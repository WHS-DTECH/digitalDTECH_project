# FOOD Room INVENTORY System

A comprehensive web application for managing recipes, class bookings, and food inventory using Flask, SQLite3, and HTML/CSS/JavaScript.

## Features

### Core Functionality
- **Recipe Management**: Add, edit, delete, and search recipes
- **Recipe Book**: Public-facing recipe browser for students and staff
- **Class Booking**: Calendar-based booking system for class cooking sessions
- **Shopping List**: Generate aggregated shopping lists from bookings, organized by teacher
- **Class Ingredients**: View and manage ingredients needed for specific classes
- **Admin Panel**: Upload staff and class data, manage recipes

### Security & Access Control
- **Google OAuth 2.0**: Secure login with Google accounts
- **Role-Based Access Control (RBAC)**: Four permission levels:
  - **VP (Vice Principal)**: Full admin access to all features
  - **DK (Teachers)**: Access to recipes, bookings, class ingredients, shopping lists
  - **MU (Booking Staff)**: Access to bookings and shopping lists
  - **Public**: Read-only access to Recipe Book (no login required)
- **Session Management**: Flask-Login for secure user sessions
- **User Profile Display**: Shows current user name and role on all pages

### Data Features
- **Unit Conversion**: Automatic conversion between metric units (g↔kg, ml↔L)
- **Data Cleaning**: Intelligent handling of measurement units and ingredient names
- **CSV Export**: Export shopping lists as CSV for spreadsheet import
- **iCal Export**: Export bookings to Google Calendar or other calendar apps
- **Print Optimization**: Print-friendly layouts for all pages

## Quick Start

### 1. Installation

```bash
# Clone the repository
cd /workspaces/FOOORMINVENTORY

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and add your Google OAuth credentials (see SETUP_OAUTH.md)
```

### 2. Setup Google OAuth (Required for Login)

Follow the detailed guide in [SETUP_OAUTH.md](SETUP_OAUTH.md) to:
1. Create a Google Cloud Project
2. Get OAuth 2.0 credentials
3. Configure environment variables

### 3. Run the Application

```bash
python app.py
```

The app will be available at `http://localhost:5000`

### 4. Initial Data Setup

1. Go to `/admin` (requires VP role or test login)
2. Upload staff CSV with columns: Code, Last Name, First Name, Email
3. Upload class CSV with columns: ClassCode, LineNo, CourseName, etc.
4. Add recipes via the admin panel or upload from URLs

## Project Structure

```
FOOORMINVENTORY/
├── app.py                 # Main Flask application
├── auth.py                # Authentication and authorization module
├── recipe_parser.py       # Recipe parsing utilities
├── recipes.db             # SQLite database
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create from .env.example)
├── .env.example          # Example environment configuration
├── SETUP_OAUTH.md        # Google OAuth setup guide
│
├── static/
│   └── styles.css        # Consolidated CSS stylesheet
│
└── templates/
    ├── login.html            # Google OAuth login page
    ├── base.html             # Base template with navigation
    ├── recbk.html            # Recipe Book (public)
    ├── recipes.html          # Recipe list and search
    ├── recipe_details.html   # Individual recipe view
    ├── class_ingred.html     # Class ingredients form
    ├── booking.html          # Booking calendar
    ├── shoplist.html         # Shopping list generator
    ├── admin.html            # Admin panel
    └── ... (other templates)
```

## User Roles & Permissions

| Feature | Public | MU | DK | VP |
|---------|--------|----|----|-----|
| View Recipes | ✓ | ✓ | ✓ | ✓ |
| Recipe Book | ✓ | ✓ | ✓ | ✓ |
| Booking Calendar | ✗ | ✓ | ✓ | ✓ |
| Shopping Lists | ✗ | ✓ | ✓ | ✓ |
| Class Ingredients | ✗ | ✗ | ✓ | ✓ |
| Admin Panel | ✗ | ✗ | ✗ | ✓ |
| Edit Recipes | ✗ | ✗ | ✗ | ✓ |
| Upload Files | ✗ | ✗ | ✗ | ✓ |

## Configuration

### Environment Variables (.env)

```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/callback
FLASK_SECRET_KEY=your-secure-random-key
FLASK_ENV=development
```

### Database

The system uses SQLite3 with automatic schema creation:
- `recipes`: Recipe data with ingredients and instructions
- `teachers`: Staff member information with role codes
- `classes`: Class/course information
- `class_bookings`: Booking records linking classes to recipes

## API Routes

### Authentication
- `GET /login` - Login page
- `GET /auth/google` - Initiate Google OAuth
- `GET /auth/callback` - Handle OAuth callback
- `GET /logout` - Logout user

### Public
- `GET /` - Home page (redirects based on auth)
- `GET /recbk` - Recipe Book (public, searchable)

### Protected (Requires Login)
- `GET /recipes` - Recipe search and management
- `GET /recipe/<id>` - Recipe details
- `GET /class_ingredients` - Class ingredients form
- `GET /booking` - Booking calendar
- `GET /shoplist` - Shopping list generator

### Admin Only
- `GET /admin` - Admin panel
- `POST /upload` - Upload recipe PDF
- `POST /uploadclass` - Upload class CSV
- `POST /admin/recipe/<id>/edit` - Edit recipe

## Troubleshooting

### Login Issues
- Ensure Google OAuth credentials are in `.env`
- Check that email domain is authorized in Google Cloud Console
- Clear browser cookies if facing state mismatch errors

### Permission Denied
- Verify user's email is in the `teachers` table
- Check that the staff code matches a configured role (VP, DK, MU)
- Role badges should appear in the top-right corner when logged in

### Database Issues
- Delete `recipes.db` to reset database with fresh schema
- Ensure SQLite3 is installed: `python -c "import sqlite3"`

## Development

### Run in Debug Mode
```bash
FLASK_ENV=development python app.py
```

### Access Database
```bash
sqlite3 recipes.db
sqlite> .tables
sqlite> .schema recipes
```

### Test Authentication Locally
Use test staff codes in `.env` or upload test staff CSV with your email

## Performance Notes

- Shopping list aggregation is calculated client-side for instant filtering
- Recipe search uses LIKE queries with index optimization
- Calendar queries limit date ranges to current year
- PDF upload processing is asynchronous

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## License

[Add appropriate license]

## Support

For issues or questions:
1. Check [SETUP_OAUTH.md](SETUP_OAUTH.md) for setup help
2. Review browser console for error messages
3. Check Flask debug output for server errors
4. Verify database and file permissions
