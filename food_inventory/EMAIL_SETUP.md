# Email Configuration for Recipe Suggestions

## Overview
The recipe suggestion feature can send emails to the VP when new recipes are suggested. This requires SMTP configuration.

## Setup on PythonAnywhere

### Option 1: Gmail SMTP (Recommended for Testing)

1. **Enable 2-Factor Authentication** on your Gmail account (if not already enabled)

2. **Create an App Password:**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and "Other (Custom name)"
   - Name it "Food Room App"
   - Copy the 16-character password

3. **Set Environment Variables** on PythonAnywhere:
   - Go to your **Web** tab
   - Scroll to **Environment variables** section
   - Add these variables:
     ```
     SMTP_SERVER = smtp.gmail.com
     SMTP_PORT = 587
     SMTP_USERNAME = your.email@gmail.com
     SMTP_PASSWORD = your-16-char-app-password
     SMTP_FROM_EMAIL = your.email@gmail.com
     ```

4. **Reload your web app**

### Option 2: School Email Server

If your school has an SMTP server:

```
SMTP_SERVER = mail.yourschool.edu
SMTP_PORT = 587
SMTP_USERNAME = your.school.email@yourschool.edu
SMTP_PASSWORD = your-email-password
SMTP_FROM_EMAIL = foodroom@yourschool.edu
```

### Option 3: SendGrid (For Production)

1. Sign up at https://sendgrid.com (free tier: 100 emails/day)
2. Create an API key
3. Set environment variables:
   ```
   SMTP_SERVER = smtp.sendgrid.net
   SMTP_PORT = 587
   SMTP_USERNAME = apikey
   SMTP_PASSWORD = your-sendgrid-api-key
   SMTP_FROM_EMAIL = noreply@yourdomain.com
   ```

## Testing

1. After setting up environment variables and reloading your web app
2. Go to the Recipes page and submit a test suggestion
3. Check your VP email inbox for the notification
4. If no email arrives, check the PythonAnywhere error log for debugging info

## Fallback Behavior

If SMTP is not configured:
- Suggestions are still saved to the database
- They appear in the Admin > Suggestions List
- No email is sent, but the system logs the email content
- User sees: "Your suggestion has been saved. The VP will review it in the Admin panel."

## Security Notes

- Never commit SMTP passwords to Git
- Use environment variables only
- Use app-specific passwords (not your main email password)
- Restrict access to environment variables on PythonAnywhere

## Troubleshooting

**"Authentication failed"**
- Check username/password are correct
- For Gmail, make sure you're using an App Password, not your regular password
- Verify 2FA is enabled on Gmail

**"Connection refused"**
- Check SMTP_SERVER and SMTP_PORT are correct
- Some networks block port 587 - try port 465 with SSL

**"Sender address rejected"**
- Make sure SMTP_FROM_EMAIL matches your authenticated account
- Some servers require the FROM address to match the login username

## Check Configuration

To verify your SMTP settings are loaded, you can check the PythonAnywhere error log after submitting a suggestion. It will show whether email was sent successfully or if credentials are missing.
