// Shared by both screens: an API answer of 401 means "sign in first". Load before app.js / review.js.
window.signInIfNeeded = res => {
  if (res.status === 401) {
    location.href = "login.html?next=" + encodeURIComponent(location.pathname.replace(/^\//, "") || "index.html");
    throw new Error("Signing in");
  }
  return res;
};
