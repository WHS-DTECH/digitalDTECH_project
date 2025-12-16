# Deploying Permission Management System to PythonAnywhere

## Overview
This guide explains how to deploy the new dynamic role permissions management system to your PythonAnywhere app.

## What's New
- **Database-driven permissions**: Role permissions are now stored in the `role_permissions` table instead of hardcoded in auth.py
- **Permission management UI**: New admin page at `/admin/permissions` to add/remove access for any role
- **Dynamic changes**: Permission changes take effect immediately without code changes

## Deployment Steps

### 1. Pull Latest Code on PythonAnywhere

```bash
cd ~/FOOORMINVENTORY
git pull origin main
```

### 2. Create the role_permissions Table

Run the setup script to create the new table with default permissions:

```bash
cd ~/FOOORMINVENTORY
python3 setup_database.py
```

This will:
- Create the `role_permissions` table if it doesn't exist
- Insert default permissions:
  - **VP**: All routes (recipes, recbk, class_ingredients, booking, shoplist, admin)
  - **DK**: All except admin (recipes, recbk, class_ingredients, booking, shoplist)
  - **MU**: Limited access (recbk, class_ingredients, booking, shoplist)
  - **public**: Recipe book only (recbk)

### 3. Reload Your Web App

Go to the PythonAnywhere **Web** tab and click the **Reload** button for `whsdtech.pythonanywhere.com`

## Using the Permission Manager

### Accessing the Manager

1. Log in as a VP user
2. Go to Admin page
3. Click **"🔐 Manage Role Permissions"** button

### Understanding the Permission Matrix

The permission matrix shows:
- **Rows**: Roles (VP, DK, MU, public)
- **Columns**: Routes/Pages (recipes, recbk, class_ingredients, booking, shoplist, admin)
- **✓** = Access granted (green)
- **✗** = Access denied (red)

### Adding/Removing Permissions

Click on any ✓ or ✗ symbol to toggle access:
- Click **✓** to remove access (will turn to ✗)
- Click **✗** to grant access (will turn to ✓)

Changes take effect immediately!

## Route Descriptions

- **recipes**: Full recipe management page (view, edit, delete recipes)
- **recbk**: Recipe Book - Browse recipes in grid or table view
- **class_ingredients**: Class ingredients calculator and ingredient management
- **booking**: Class booking system for scheduling
- **shoplist**: Shopping list generator for classes
- **admin**: Administrative functions (staff/class upload, recipe management, permissions)

## Important Notes

### Security Recommendations

1. **VP role** should always have access to all pages, especially admin
2. **Admin page** access should be restricted to VP only
3. **Public role** controls what non-authenticated users can see
4. Be careful removing your own access - you could lock yourself out!

### Default Permissions

The system starts with these defaults:

| Role   | Description    | Default Access                                                    |
|--------|----------------|-------------------------------------------------------------------|
| VP     | Vice Principal | ALL pages (recipes, recbk, class_ingredients, booking, shoplist, admin) |
| DK     | Teacher        | Most pages except admin                                           |
| MU     | Booking Staff  | Limited (recbk, class_ingredients, booking, shoplist)            |
| public | Non-logged in  | Recipe book only (recbk)                                         |

### Troubleshooting

**Permission changes not working?**
- Make sure you reloaded the web app after running setup_database.py
- Check that the role_permissions table exists: `sqlite3 ~/FOOORMINVENTORY/recipes.db "SELECT * FROM role_permissions;"`

**Table already exists error?**
- This is normal! The setup script uses `CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE`
- Existing data won't be affected

**Lost admin access?**
- If you accidentally remove VP access to admin, you'll need to fix it via SSH:
  ```bash
  sqlite3 ~/FOOORMINVENTORY/recipes.db "INSERT OR IGNORE INTO role_permissions (role, route) VALUES ('VP', 'admin');"
  ```

## Database Schema

The new `role_permissions` table:

```sql
CREATE TABLE IF NOT EXISTS role_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    route TEXT NOT NULL,
    UNIQUE(role, route)
);
```

## Testing

1. Log in as VP and access the permission manager
2. Try removing DK access to "recipes"
3. Log in as a DK user and verify they can't access the Recipes page
4. Add the permission back and verify access is restored

## Rollback (If Needed)

If you need to revert to hardcoded permissions:

1. In `auth.py`, change `has_access()` method back to:
   ```python
   def has_access(self, endpoint):
       role = self.role
       if role not in ROLE_PERMISSIONS:
           return False
       return endpoint in ROLE_PERMISSIONS[role]['routes']
   ```

2. Reload the web app

The ROLE_PERMISSIONS dictionary is still in the code as a fallback, so the system will work even if the database table doesn't exist.
