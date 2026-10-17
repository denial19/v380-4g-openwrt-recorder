# Publish from OpenWrt (SSH terminal, no computer)

1. Verify `src/` was sanitized and source files compiled; inspect `git status` before commit.
2. Install tooling: `apk add git openssh-client openssh-keygen`.
3. Create a GitHub **empty** public repository named `v380-4g-openwrt-recorder` from https://github.com/new (do not add README/license online).
4. Generate an independent deploy SSH key on OpenWrt: `mkdir -p /root/.ssh && chmod 700 /root/.ssh && ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519_github -N '' -C openwrt-v380`.
5. Add the **public key** from `cat /root/.ssh/id_ed25519_github.pub` to the repository Settings → Deploy keys → Add deploy key, **check Allow write access**. Never share the private key.
6. From the repository directory: `git init -b main` (or `git init; git branch -M main`); `git add .gitignore README.md README.ru.md LICENSE SECURITY.md PUBLISHING.md config.example.json src scripts`.
7. Verify `git diff --cached --name-only` and `git diff --cached --check`. Use `git commit -m 'Initial experimental OpenWrt V380 recorder'`.
8. `git remote add origin git@github.com:YOUR_GITHUB_USERNAME/v380-4g-openwrt-recorder.git`.
9. Use `GIT_SSH_COMMAND='ssh -i /root/.ssh/id_ed25519_github -o IdentitiesOnly=yes' git push -u origin main`.

For the first connection, compare GitHub's official SSH host key fingerprint with the displayed value before accepting it.

A GitHub deploy key is **repository-scoped**, safer than storing an account-wide personal access token on the router. Revoke it in GitHub Settings → Deploy keys if you retire the router.
