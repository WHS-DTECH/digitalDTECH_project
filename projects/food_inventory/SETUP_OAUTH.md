# Google OAuth 2.0 Setup Guide

This document explains how to set up Google OAuth 2.0 authentication for the Food Room Inventory system.

## Prerequisites

- Google Cloud Project (create one at https://console.cloud.google.com)
- Administrator access to the project

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click the project dropdown and select "New Project"
3. Enter a project name (e.g., "Food Room Inventory")
4. Click "Create"

## Step 2: Enable Google+ API

1. In the Cloud Console, go to **APIs & Services** > **Library**
2. Search for "Google+ API" (or "Google Identity API")
3. Click on it and select **Enable**

## Step 3: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth 2.0 Client ID**
3. If prompted, configure the OAuth consent screen first:
   - User Type: External
   - App name: "Food Room Inventory"
   - User support email: your-email@example.com
   - Developer contact: your-email@example.com
4. Back in Credentials, click **Create Credentials** > **OAuth 2.0 Client ID** again
5. Application type: **Web application**
6. Name: "Food Room"
7. Authorized JavaScript origins:
   - http://localhost:5000 (for development)
   - https://yourdomain.com (for production)
8. Authorized redirect URIs:
   - http://localhost:5000/auth/callback (for development)
   - https://yourdomain.com/auth/callback (for production)
9. Click **Create**
10. Copy the **Client ID** and **Client Secret** from the dialog

## Step 4: Configure Environment Variables

1. Create a `.env` file in the project root (if it doesn't exist):

```bash
GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/callback
FLASK_SECRET_KEY=your-secure-random-key-here
FLASK_ENV=development
```

2. **Never commit `.env` to version control!** It's already in `.gitignore`.

## Step 5: Map Staff Codes to Users

Users' staff codes are automatically looked up from their email address in the `teachers` table:

- **Upload staff CSV** via the Admin page with columns: `Code`, `Last Name`, `First Name`, `Email`
- The system will match the Google account email to the `Email` column
- If a match is found, the user's `Code` determines their role

### Role Mapping:

- **VP (Vice Principal)**: Full admin access to all features
- **DK**: Teacher access (recipes, class ingredients, booking, shopping list)
- **MU**: Booking staff access (booking calendar, shopping list)
- **No code**: Public access (recipe book only, no login required)

## Step 6: Testing

1. Start the Flask app:
```bash
python app.py
```

2. Navigate to http://localhost:5000/login
3. Click "Sign in with Google"
4. You should be redirected back to the app with your user profile

## Troubleshooting

### Issue: "Invalid redirect URI"
- Check that your redirect URI in `.env` matches exactly what you configured in Google Cloud Console
- Include the full URI including `http://` and the port number

### Issue: "OAuth state mismatch"
- Make sure you're using the same browser session
- Check that `FLASK_SECRET_KEY` is configured
- Try clearing browser cookies

### Issue: User logs in but can't see any pages
- Check that the user's email is in the `teachers` table with a matching code
- Verify the staff code exists in the ROLE_PERMISSIONS dictionary
- Check browser console for any error messages

### Issue: "Google OAuth is not configured"
- Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in `.env`
- Reload the Flask app after changing `.env`

## Production Deployment

When deploying to production:

1. Update `GOOGLE_REDIRECT_URI` to your production domain
2. Add production domain to Google OAuth credentials
3. Use a secure `FLASK_SECRET_KEY` (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
4. Set `FLASK_ENV=production`
5. Use a production WSGI server (Gunicorn, uWSGI, etc.)

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Flask-Login Documentation](https://flask-login.readthedocs.io/)
- [Google OAuth Scopes](https://developers.google.com/identity/protocols/oauth2/scopes#google_oauth_20_scopes)
