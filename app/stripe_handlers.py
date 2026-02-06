"""
Stripe integration handlers for ICENews premium subscriptions.

Handles checkout sessions, webhooks, and customer portal.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

import stripe

from app.db import (
    get_user_by_email,
    create_or_get_user,
    update_user_premium_status,
    add_premium_user,
)

# Configure Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")  # €5/month subscription price ID
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# Subscription price in EUR (for display purposes)
SUBSCRIPTION_PRICE_EUR = 5


def create_checkout_session(user_email: str, user_id: int) -> Optional[str]:
    """
    Create a Stripe checkout session for premium subscription.
    
    Args:
        user_email: User's email address
        user_id: User's database ID
    
    Returns:
        Checkout session URL or None if error
    """
    if not stripe.api_key or not STRIPE_PRICE_ID:
        print("[STRIPE] Missing API key or price ID configuration")
        return None
    
    try:
        # Check if customer already exists
        existing_customers = stripe.Customer.list(email=user_email, limit=1)
        
        if existing_customers.data:
            customer = existing_customers.data[0]
        else:
            # Create new customer
            customer = stripe.Customer.create(
                email=user_email,
                metadata={"user_id": str(user_id)}
            )
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=customer.id,
            mode="subscription",
            payment_method_types=["card"],
            line_items=[
                {
                    "price": STRIPE_PRICE_ID,
                    "quantity": 1,
                }
            ],
            success_url=f"{APP_BASE_URL}/downloads?checkout=success",
            cancel_url=f"{APP_BASE_URL}/?checkout=cancelled",
            metadata={
                "user_id": str(user_id),
                "user_email": user_email,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(user_id),
                    "user_email": user_email,
                }
            },
        )
        
        return session.url
    
    except stripe.error.StripeError as e:
        print(f"[STRIPE] Checkout session error: {e}")
        return None


def create_portal_session(customer_id: str) -> Optional[str]:
    """
    Create a Stripe customer portal session for managing subscription.
    
    Args:
        customer_id: Stripe customer ID
    
    Returns:
        Portal session URL or None if error
    """
    if not stripe.api_key:
        return None
    
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{APP_BASE_URL}/downloads",
        )
        return session.url
    except stripe.error.StripeError as e:
        print(f"[STRIPE] Portal session error: {e}")
        return None


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Handle Stripe webhook events.
    
    Args:
        payload: Raw webhook payload
        sig_header: Stripe signature header
    
    Returns:
        Dict with 'success' boolean and 'message' string
    """
    if not STRIPE_WEBHOOK_SECRET:
        return {"success": False, "message": "Webhook secret not configured"}
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return {"success": False, "message": "Invalid payload"}
    except stripe.error.SignatureVerificationError:
        return {"success": False, "message": "Invalid signature"}
    
    event_type = event["type"]
    data = event["data"]["object"]
    
    print(f"[STRIPE] Received webhook: {event_type}")
    
    # Handle different event types
    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(data)
    
    elif event_type == "customer.subscription.created":
        return _handle_subscription_created(data)
    
    elif event_type == "customer.subscription.updated":
        return _handle_subscription_updated(data)
    
    elif event_type == "customer.subscription.deleted":
        return _handle_subscription_deleted(data)
    
    elif event_type == "invoice.payment_failed":
        return _handle_payment_failed(data)
    
    elif event_type == "invoice.payment_succeeded":
        return _handle_payment_succeeded(data)
    
    # Unhandled event type
    return {"success": True, "message": f"Unhandled event type: {event_type}"}


def _handle_checkout_completed(session: dict) -> dict:
    """Handle successful checkout completion."""
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    user_email = session.get("metadata", {}).get("user_email")
    
    if not user_email:
        # Try to get email from customer
        try:
            customer = stripe.Customer.retrieve(customer_id)
            user_email = customer.email
        except:
            pass
    
    if user_email:
        # Ensure user exists
        user = create_or_get_user(user_email)
        
        # Calculate expiration (1 month from now)
        expires_at = (datetime.now() + timedelta(days=30)).isoformat()
        
        # Update premium status
        update_user_premium_status(
            email=user_email,
            is_premium=True,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            premium_expires_at=expires_at
        )
        
        # Also update legacy premium_users table for compatibility
        add_premium_user(user_email, "premium", expires_at)
        
        print(f"[STRIPE] Premium granted to {user_email}")
        return {"success": True, "message": f"Premium granted to {user_email}"}
    
    return {"success": False, "message": "Could not identify user"}


def _handle_subscription_created(subscription: dict) -> dict:
    """Handle new subscription creation."""
    customer_id = subscription.get("customer")
    subscription_id = subscription.get("id")
    status = subscription.get("status")
    
    user_email = subscription.get("metadata", {}).get("user_email")
    
    if not user_email:
        try:
            customer = stripe.Customer.retrieve(customer_id)
            user_email = customer.email
        except:
            pass
    
    if user_email and status == "active":
        # Get current period end
        current_period_end = subscription.get("current_period_end")
        expires_at = datetime.fromtimestamp(current_period_end).isoformat() if current_period_end else None
        
        update_user_premium_status(
            email=user_email,
            is_premium=True,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            premium_expires_at=expires_at
        )
        
        add_premium_user(user_email, "premium", expires_at)
        return {"success": True, "message": f"Subscription created for {user_email}"}
    
    return {"success": True, "message": "Subscription created"}


def _handle_subscription_updated(subscription: dict) -> dict:
    """Handle subscription updates (renewals, plan changes)."""
    customer_id = subscription.get("customer")
    subscription_id = subscription.get("id")
    status = subscription.get("status")
    
    user_email = subscription.get("metadata", {}).get("user_email")
    
    if not user_email:
        try:
            customer = stripe.Customer.retrieve(customer_id)
            user_email = customer.email
        except:
            pass
    
    if user_email:
        is_premium = status in ["active", "trialing"]
        current_period_end = subscription.get("current_period_end")
        expires_at = datetime.fromtimestamp(current_period_end).isoformat() if current_period_end else None
        
        update_user_premium_status(
            email=user_email,
            is_premium=is_premium,
            stripe_subscription_id=subscription_id,
            premium_expires_at=expires_at
        )
        
        if is_premium:
            add_premium_user(user_email, "premium", expires_at)
        
        return {"success": True, "message": f"Subscription updated for {user_email}"}
    
    return {"success": True, "message": "Subscription updated"}


def _handle_subscription_deleted(subscription: dict) -> dict:
    """Handle subscription cancellation."""
    customer_id = subscription.get("customer")
    user_email = subscription.get("metadata", {}).get("user_email")
    
    if not user_email:
        try:
            customer = stripe.Customer.retrieve(customer_id)
            user_email = customer.email
        except:
            pass
    
    if user_email:
        # Revoke premium access
        update_user_premium_status(
            email=user_email,
            is_premium=False,
            premium_expires_at=None
        )
        
        print(f"[STRIPE] Premium revoked from {user_email}")
        return {"success": True, "message": f"Premium revoked from {user_email}"}
    
    return {"success": True, "message": "Subscription deleted"}


def _handle_payment_failed(invoice: dict) -> dict:
    """Handle failed payment."""
    customer_id = invoice.get("customer")
    
    try:
        customer = stripe.Customer.retrieve(customer_id)
        user_email = customer.email
        print(f"[STRIPE] Payment failed for {user_email}")
        # Note: We don't immediately revoke access - Stripe handles retry logic
        return {"success": True, "message": f"Payment failed for {user_email}"}
    except:
        return {"success": True, "message": "Payment failed"}


def _handle_payment_succeeded(invoice: dict) -> dict:
    """Handle successful payment (renewal)."""
    customer_id = invoice.get("customer")
    subscription_id = invoice.get("subscription")
    
    try:
        customer = stripe.Customer.retrieve(customer_id)
        user_email = customer.email
        
        if user_email and subscription_id:
            # Get subscription details for expiration
            subscription = stripe.Subscription.retrieve(subscription_id)
            current_period_end = subscription.get("current_period_end")
            expires_at = datetime.fromtimestamp(current_period_end).isoformat() if current_period_end else None
            
            update_user_premium_status(
                email=user_email,
                is_premium=True,
                premium_expires_at=expires_at
            )
            
            add_premium_user(user_email, "premium", expires_at)
            
            print(f"[STRIPE] Payment succeeded for {user_email}, renewed until {expires_at}")
            return {"success": True, "message": f"Payment succeeded for {user_email}"}
    except:
        pass
    
    return {"success": True, "message": "Payment succeeded"}


def get_subscription_status(user_email: str) -> dict:
    """
    Get subscription status for a user.
    
    Returns dict with subscription info or None if no subscription.
    """
    user = get_user_by_email(user_email)
    if not user:
        return {"has_subscription": False}
    
    stripe_customer_id = user.get("stripe_customer_id")
    if not stripe_customer_id or not stripe.api_key:
        return {
            "has_subscription": False,
            "is_premium": bool(user.get("is_premium")),
            "expires_at": user.get("premium_expires_at"),
        }
    
    try:
        subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,
            status="active",
            limit=1
        )
        
        if subscriptions.data:
            sub = subscriptions.data[0]
            return {
                "has_subscription": True,
                "is_premium": True,
                "subscription_id": sub.id,
                "status": sub.status,
                "current_period_end": datetime.fromtimestamp(sub.current_period_end).isoformat(),
                "cancel_at_period_end": sub.cancel_at_period_end,
            }
        
        return {
            "has_subscription": False,
            "is_premium": bool(user.get("is_premium")),
            "expires_at": user.get("premium_expires_at"),
        }
    
    except stripe.error.StripeError as e:
        print(f"[STRIPE] Error getting subscription status: {e}")
        return {
            "has_subscription": False,
            "is_premium": bool(user.get("is_premium")),
            "error": str(e),
        }
