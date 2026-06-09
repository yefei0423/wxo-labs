e# 🚀 GitHub Pages Deployment Guide

Quick guide to deploy the WXO Labs Tutorial website to GitHub Pages.

## Prerequisites

- GitHub repository with the WXO Test Tools
- Admin access to repository settings
- Files in the `/docs` directory

## Step-by-Step Deployment

### 1. Push Files to GitHub

Ensure all files are committed and pushed:

```bash
git add docs/
git commit -m "Add GitHub Pages tutorial site"
git push origin main
```

### 2. Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** (top right)
3. Scroll down to **Pages** section (left sidebar)
4. Under **Source**:
   - Branch: Select `main` (or your default branch)
   - Folder: Select `/docs`
5. Click **Save**

### 3. Wait for Deployment

- GitHub Actions will automatically build your site
- Check the **Actions** tab to see deployment progress
- Usually takes 1-3 minutes
- You'll see a green checkmark when complete

### 4. Access Your Site

Your site will be available at:
```
https://[your-username].github.io/[repository-name]/
```

For example:
```
https://mvankempen.github.io/WxO-ToolBox/
```

## Verification Checklist

After deployment, verify:

- [ ] Site loads without errors
- [ ] Navigation works (click all menu items)
- [ ] All lab cards are visible
- [ ] Styles are applied correctly
- [ ] JavaScript features work (scroll animations, hover effects)
- [ ] Mobile responsive (test on phone or resize browser)
- [ ] Links to GitHub repo work
- [ ] Footer information is correct

## Troubleshooting

### Site Shows 404 Error

**Problem:** Page not found after enabling GitHub Pages

**Solutions:**
1. Wait 2-3 minutes for initial deployment
2. Check that `/docs` folder is selected in settings
3. Verify `index.html` exists in `/docs` directory
4. Try accessing with trailing slash: `https://...github.io/repo/`

### Styles Not Loading

**Problem:** Site loads but looks unstyled

**Solutions:**
1. Check browser console for errors (F12)
2. Verify `styles.css` path in `index.html`
3. Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
4. Check that `styles.css` was committed to repo

### JavaScript Not Working

**Problem:** Animations or interactive features don't work

**Solutions:**
1. Check browser console for JavaScript errors
2. Verify `script.js` is loaded (check Network tab in DevTools)
3. Ensure browser supports ES6+ (update browser if needed)
4. Test in different browser (Chrome, Firefox, Safari)

### Links Are Broken

**Problem:** Internal links don't work or go to wrong pages

**Solutions:**
1. Update `baseurl` in `_config.yml` to match your repo name
2. Use relative paths for internal links
3. Test all navigation links after deployment

## Custom Domain (Optional)

To use a custom domain like `wxo-labs.example.com`:

### 1. Add CNAME File

Create `docs/CNAME` with your domain:
```
wxo-labs.example.com
```

### 2. Configure DNS

Add DNS records with your domain provider:

**For apex domain (example.com):**
```
A Record: 185.199.108.153
A Record: 185.199.109.153
A Record: 185.199.110.153
A Record: 185.199.111.153
```

**For subdomain (wxo-labs.example.com):**
```
CNAME Record: [your-username].github.io
```

### 3. Enable HTTPS

In GitHub Pages settings:
- Wait for DNS to propagate (can take 24-48 hours)
- Check "Enforce HTTPS"

## Updates and Maintenance

### Making Changes

1. Edit files locally in `/docs` directory
2. Test locally (see Local Development below)
3. Commit and push changes:
   ```bash
   git add docs/
   git commit -m "Update tutorial content"
   git push origin main
   ```
4. GitHub Pages will automatically rebuild (1-2 minutes)

### Local Development

Test changes before deploying:

**Option 1: Python HTTP Server**
```bash
cd docs
python3 -m http.server 8000
# Visit: http://localhost:8000
```

**Option 2: VS Code Live Server**
1. Install "Live Server" extension
2. Right-click `docs/index.html`
3. Select "Open with Live Server"

**Option 3: Node.js**
```bash
npx http-server docs -p 8000
```

## Performance Optimization

### Enable Caching

GitHub Pages automatically handles caching, but you can optimize:

1. **Minimize CSS/JS** (optional):
   ```bash
   # Install minifier
   npm install -g clean-css-cli uglify-js
   
   # Minify CSS
   cleancss -o docs/styles.min.css docs/styles.css
   
   # Minify JS
   uglifyjs docs/script.js -o docs/script.min.js
   
   # Update index.html to use .min files
   ```

2. **Optimize Images** (if you add any):
   - Use WebP format
   - Compress with tools like TinyPNG
   - Use appropriate dimensions

### Monitor Performance

Use these tools to check site performance:

- [Google PageSpeed Insights](https://pagespeed.web.dev/)
- [GTmetrix](https://gtmetrix.com/)
- Chrome DevTools Lighthouse (F12 → Lighthouse tab)

## Analytics (Optional)

### Add Google Analytics

1. Get GA4 tracking ID from [Google Analytics](https://analytics.google.com/)

2. Add to `docs/index.html` before `</head>`:

```html
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

3. Update `docs/_config.yml`:
```yaml
google_analytics: G-XXXXXXXXXX
```

## Security

### Best Practices

- ✅ Enable HTTPS (enforced by default)
- ✅ Don't commit sensitive data (API keys, passwords)
- ✅ Use environment variables for secrets
- ✅ Keep dependencies updated
- ✅ Review external links regularly

### Content Security Policy (Optional)

Add to `index.html` `<head>`:

```html
<meta http-equiv="Content-Security-Policy" 
      content="default-src 'self'; 
               script-src 'self' 'unsafe-inline' https://www.googletagmanager.com; 
               style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; 
               font-src 'self' https://fonts.gstatic.com;">
```

## Backup and Version Control

### Create Backup

```bash
# Create backup branch
git checkout -b backup-docs-$(date +%Y%m%d)
git push origin backup-docs-$(date +%Y%m%d)
git checkout main
```

### Rollback if Needed

```bash
# View commit history
git log --oneline docs/

# Rollback to specific commit
git checkout <commit-hash> -- docs/
git commit -m "Rollback docs to previous version"
git push origin main
```

## Support

### Getting Help

- **GitHub Issues:** Report bugs or request features
- **GitHub Discussions:** Ask questions and share ideas
- **Documentation:** Check [GitHub Pages docs](https://docs.github.com/en/pages)

### Common Resources

- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [Jekyll Documentation](https://jekyllrb.com/docs/)
- [Markdown Guide](https://www.markdownguide.org/)
- [HTML/CSS/JS Reference](https://developer.mozilla.org/)

---

## Quick Reference Commands

```bash
# Test locally
cd docs && python3 -m http.server 8000

# Commit and deploy
git add docs/
git commit -m "Update tutorial site"
git push origin main

# Check deployment status
# Visit: https://github.com/[username]/[repo]/actions

# View live site
# Visit: https://[username].github.io/[repo]/
```

---

**Need help?** Contact: mvk@ca.ibm.com

*No bug too small, no syntax too weird.* 🏢🤏