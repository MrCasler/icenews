/**
 * ICENews – Alpine.js data and behavior
 * 
 * Features:
 * - Post feed with filtering
 * - Like button (stored in localStorage, tracked via Umami)
 * - Share button (Web Share API or clipboard, tracked via Umami)
 * - Clickable cards (open tweet, tracked via Umami)
 */
function _icenewsDebugEnabled() {
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get("debug") === "1") return true;
  } catch {
    // ignore
  }
  try {
    return localStorage.getItem("icenews_debug") === "1";
  } catch {
    return false;
  }
}

function _icenewsLog(...args) {
  if (!_icenewsDebugEnabled()) return;
  // Use console.debug so it’s easy to filter in devtools.
  // Avoid logging full post text by default (safety + noise).
  console.debug("[ICENews]", ...args);
}

function _safeParseJson(value, fallback) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function _safeLoadLikes() {
  // localStorage can be unavailable (privacy mode) or contain corrupted JSON.
  try {
    const raw = localStorage.getItem("icenews_likes");
    const parsed = _safeParseJson(raw || "{}", {});
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return parsed;
  } catch {
    return {};
  }
}

function iceNews() {
  return {
    posts: [],
    total: 0,
    category: "",
    loading: false,
    likes: _safeLoadLikes(),
    toast: { show: false, message: "" },
    isPremium: false, // Set by server via x-init
    menuOpen: false, // Hamburger menu state

    init() {
      _icenewsLog("init() called");
      // Initialize state from server-rendered JSON
      const postsEl = document.getElementById("initial-posts");
      _icenewsLog("initial-posts element", { found: !!postsEl, length: postsEl?.textContent?.length || 0 });
      if (postsEl && postsEl.textContent) {
        try {
          const parsed = JSON.parse(postsEl.textContent);
          if (Array.isArray(parsed)) {
            this.posts = parsed;
          } else {
            _icenewsLog("initial-posts JSON was not an array");
          }
          _icenewsLog("initial posts parsed", {
            count: Array.isArray(parsed) ? parsed.length : 0,
            first: Array.isArray(parsed) && parsed[0] ? { post_id: parsed[0].post_id, url: parsed[0].url } : null,
          });
        } catch (e) {
          _icenewsLog("initial-posts JSON parse failed", { error: e?.message || String(e) });
          this.posts = [];
        }
      }

      const totalEl = document.getElementById("initial-total");
      if (totalEl && totalEl.textContent) {
        const n = Number(totalEl.textContent);
        if (!Number.isNaN(n)) this.total = n;
      }

      // Evidence-backed fallback: if server JSON is missing/broken, load via API automatically.
      if (!Array.isArray(this.posts) || this.posts.length === 0) {
        _icenewsLog("no initial posts; auto-fetching from /api/posts");
        this.fetchPosts();
      } else {
        _icenewsLog("init complete", { postsCount: this.posts.length, total: this.total });
      }
    },

    fetchPosts() {
      _icenewsLog("fetchPosts()", { category: this.category || "" });
      this.loading = true;
      const params = new URLSearchParams({ limit: 50, offset: 0 });
      if (this.category) params.set("category", this.category);
      fetch("/api/posts?" + params.toString(), { headers: { Accept: "application/json" } })
        .then(async (r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return await r.json();
        })
        .then((data) => {
          this.posts = data.posts || [];
          this.total = data.total ?? 0;
          _icenewsLog("fetchPosts success", { postsCount: this.posts.length, total: this.total });
        })
        .catch((e) => {
          _icenewsLog("fetchPosts failed", { error: e?.message || String(e) });
          this.posts = [];
        })
        .finally(() => {
          this.loading = false;
        });
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Like functionality (server-side global count + local client state)
    // ──────────────────────────────────────────────────────────────────────────
    isLiked(postId) {
      return !!this.likes[postId];
    },

    async toggleLike(post) {
      _icenewsLog("toggleLike()", { post_id: post?.post_id });
      if (!post || !post.post_id) return;
      const postId = post.post_id;
      const wasLiked = this.isLiked(postId);
      const endpoint = wasLiked ? "unlike" : "like";
      
      // Optimistic update: update UI immediately
      const oldCount = post.like_count || 0;
      const newCount = wasLiked ? Math.max(0, oldCount - 1) : oldCount + 1;
      post.like_count = newCount;
      
      if (wasLiked) {
        delete this.likes[postId];
      } else {
        this.likes[postId] = true;
      }
      
      try {
        localStorage.setItem("icenews_likes", JSON.stringify(this.likes));
      } catch {
        // ignore (storage may be unavailable)
      }
      
      // Track the event
      this.trackEvent(endpoint, { post_id: postId, author: post.author_handle });
      
      // Sync with server (reconcile if server count differs)
      try {
        const resp = await fetch(`/api/posts/${encodeURIComponent(postId)}/${endpoint}`, {
          method: "POST",
          headers: { Accept: "application/json" },
        });
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const data = await resp.json();
        // Reconcile: use server's authoritative count
        post.like_count = data.like_count ?? newCount;
        _icenewsLog(`toggleLike ${endpoint} success`, { post_id: postId, like_count: data.like_count });
      } catch (e) {
        _icenewsLog(`toggleLike ${endpoint} failed`, { error: e?.message || String(e) });
        // Rollback optimistic update
        post.like_count = oldCount;
        if (wasLiked) {
          this.likes[postId] = true;
        } else {
          delete this.likes[postId];
        }
        try {
          localStorage.setItem("icenews_likes", JSON.stringify(this.likes));
        } catch {
          // ignore
        }
        this.showToast("Could not sync like with server");
      }
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Share functionality
    // ──────────────────────────────────────────────────────────────────────────
    async sharePost(post) {
      _icenewsLog("sharePost()", { post_id: post?.post_id, hasUrl: !!post?.url });
      if (!post || !post.post_id) return;
      const url = post.url;
      if (!url) {
        this.showToast("No link available to share");
        return;
      }
      const author = post.author_display_name || post.author_handle || "Unknown";
      const body = typeof post.text === "string" ? post.text : "";
      const text = `${author}: ${body.slice(0, 100)}...`;

      this.trackEvent("share", { post_id: post.post_id, author: post.author_handle });

      // Try Web Share API first (mobile/modern browsers)
      if (navigator.share) {
        try {
          await navigator.share({ title: "ICENews", text, url });
          return;
        } catch {
          // User cancelled or error - fall through to clipboard
        }
      }

      // Fallback: copy link to clipboard
      try {
        await navigator.clipboard.writeText(url);
        this.showToast("Link copied to clipboard!");
      } catch (e) {
        _icenewsLog("sharePost clipboard failed", { error: e?.message || String(e) });
        this.showToast("Could not copy link");
      }
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Open post (click card → open tweet)
    // ──────────────────────────────────────────────────────────────────────────
    openPost(post) {
      _icenewsLog("openPost()", { post_id: post?.post_id, hasUrl: !!post?.url });
      if (!post || !post.post_id) return;
      this.trackEvent("open_post", { post_id: post.post_id, author: post.author_handle });
      if (!post.url) {
        this.showToast("No link available to open");
        return;
      }
      window.open(post.url, "_blank", "noopener,noreferrer");
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Toast notification
    // ──────────────────────────────────────────────────────────────────────────
    showToast(message) {
      this.toast.message = message;
      this.toast.show = true;
      setTimeout(() => {
        this.toast.show = false;
      }, 2500);
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Download functionality (available to everyone)
    // Premium users can also save downloads to their gallery
    // ──────────────────────────────────────────────────────────────────────────
    async downloadPost(post) {
      _icenewsLog("downloadPost()", { post_id: post?.post_id, isPremium: this.isPremium });
      
      if (!post || !post.post_id) return;
      
      // Downloads are available to everyone
      this.trackEvent("download_attempt", { post_id: post.post_id, author: post.author_handle, isPremium: this.isPremium });
      
      try {
        const resp = await fetch(`/api/posts/${encodeURIComponent(post.post_id)}/download`, {
          method: "GET",
          headers: { Accept: "*/*" },
        });
        
        if (!resp.ok) {
          const errorData = await resp.json().catch(() => ({}));
          throw new Error(errorData.detail || `HTTP ${resp.status}`);
        }
        
        // Get filename from Content-Disposition header or generate one
        const contentDisposition = resp.headers.get("Content-Disposition");
        let filename = "download";
        if (contentDisposition) {
          const matches = /filename="?([^"]+)"?/.exec(contentDisposition);
          if (matches && matches[1]) {
            filename = matches[1];
          }
        }
        
        // Download the file
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        if (this.isPremium) {
          this.showToast("Download started & saved to your gallery!");
        } else {
          this.showToast("Download started!");
        }
        this.trackEvent("download_success", { post_id: post.post_id, author: post.author_handle, isPremium: this.isPremium });
        
      } catch (e) {
        _icenewsLog("downloadPost failed", { error: e?.message || String(e) });
        this.showToast(e.message || "Download failed");
        this.trackEvent("download_failed", { post_id: post.post_id, error: e.message });
      }
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Premium upgrade prompt (for non-premium users clicking premium features)
    // ──────────────────────────────────────────────────────────────────────────
    showUpgradePrompt() {
      _icenewsLog("showUpgradePrompt()");
      this.trackEvent("upgrade_prompt_shown");
      
      // Show toast with upgrade message
      this.showToast("Sign in and subscribe for premium downloads");
      
      // Redirect to login after a short delay
      setTimeout(() => {
        window.location.href = "/auth/login";
      }, 1500);
    },

    // ──────────────────────────────────────────────────────────────────────────
    // Umami event tracking (no-op if Umami not loaded)
    // ──────────────────────────────────────────────────────────────────────────
    trackEvent(eventName, eventData = {}) {
      // Umami exposes window.umami when loaded
      if (typeof window.umami !== "undefined" && typeof window.umami.track === "function") {
        window.umami.track(eventName, eventData);
      }
    },
  };
}
