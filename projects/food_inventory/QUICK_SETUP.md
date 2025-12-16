# Quick Reference: Google OAuth Setup

## 🚀 30-Second Setup

### Step 1: Get Google Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project → "Food Room Inventory"
3. APIs & Services → Library → Enable "Google+ API"
4. Credentials → Create OAuth 2.0 Web Application
5. Copy Client ID and Client Secret

### Step 2: Configure App
1. Edit `.env` file:
```
GOOGLE_CLIENT_ID=your-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-secret
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/callback
FLASK_SECRET_KEY=generate-random-string
```

### Step 3: Upload Staff Data
1. Run: `python app.py`
2. Go to http://localhost:5000/login
3. Will say "not configured" → go to `/admin`
4. Upload CSV with: Code, Last Name, First Name, Email
5. Use codes: **VP** (admin), **DK** (teacher), **MU** (booking staff)

### Step 4: Test Login
1. Go to http://localhost:5000/login
2. Click "Sign in with Google"
3. Use account matching email in staff CSV
4. See role badge in top-right corner

## 📋 Staff CSV Format

```csv
Code,Last Name,First Name,Email
VP,Admin,TestUser,admin@school.edu
DK,Teacher,JohnSmith,jsmith@school.edu
MU,Staff,MaryJones,mjones@school.edu
```

## 🔐 Roles & Access

| Role | Can Access |
|------|-----------|
| **VP** | Everything + Admin |
| **DK** | Recipes, Booking, Shopping, Class |
| **MU** | Booking, Shopping |
| **No Code** | Recipe Book only (public) |

## 🔧 Configuration Files

### `.env` (Required for Login)
```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/callback
FLASK_SECRET_KEY=your-secure-key
FLASK_ENV=development
```

### `.env.example` (Template)
Copy this and fill in your Google credentials

## 🌐 Navigation After Login

### All Authenticated Users See:
- Dashboard (redirects to class ingredients or recipe book)
- Recipes
- Recipe Book
- User name + role badge
- Logout button

### DK (Teacher) Also Sees:
- Class Ingredients
- Booking Calendar
- Shopping List

### VP (Admin) Also Sees:
- Admin Panel (staff, classes, recipes, upload)

### Public Users (Not Logged In) See:
- Recipe Book only
- Login link

## ✅ Security Features

- ✅ Google OAuth 2.0 standard
- ✅ CSRF protection (state tokens)
- ✅ Role-based access control
- ✅ Secure session management
- ✅ Email-based authentication
- ✅ Server-side permission checking

## 🐛 Common Issues & Fixes

| Issue | Solution |
|-------|----------|
| "Not configured" | Add GOOGLE_CLIENT_ID & SECRET to .env |
| "Invalid redirect URI" | Ensure GOOGLE_REDIRECT_URI matches exactly in Google Console |
| "State mismatch" | Clear browser cookies, try again |
| "Permission denied" | Add user email to staff CSV upload |
| "No role badge" | Restart app, refresh page |

## 📚 Documentation Files

- **SETUP_OAUTH.md** - Detailed step-by-step guide
- **SECURITY_IMPLEMENTATION.md** - Technical implementation details
- **README_NEW.md** - Full project documentation

## 🎯 Testing Checklist

- [ ] Google OAuth credentials created
- [ ] `.env` file configured with credentials
- [ ] Staff CSV uploaded with test accounts
- [ ] Can login with test Google account
- [ ] Role badge shows correct role
- [ ] Can access appropriate pages for each role
- [ ] Logout works correctly
- [ ] Public access to Recipe Book works

## 🚀 Production Checklist

- [ ] Update GOOGLE_REDIRECT_URI to production domain
- [ ] Add production domain to Google OAuth authorized URIs
- [ ] Generate secure FLASK_SECRET_KEY
- [ ] Set FLASK_ENV=production
- [ ] Use WSGI server (Gunicorn, etc.)
- [ ] Enable HTTPS
- [ ] Back up database regularly
- [ ] Test all roles in production environment
- [ ] Monitor error logs

## 📞 Quick Links

- [Google Cloud Console](https://console.cloud.google.com)
- [OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Flask-Login Docs](https://flask-login.readthedocs.io/)

---

**Ready to set up?** Start with [SETUP_OAUTH.md](SETUP_OAUTH.md) for detailed instructions!
