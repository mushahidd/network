# ConnectHub - Community Business Network Platform

A modern platform where users can create business listings and professional profiles to connect with their community.

## Features

- 🔐 **Multiple Authentication Options:**
  - Email/Password authentication with bcrypt
  - Google OAuth 2.0
  - Microsoft OAuth 2.0
- 🏢 Business listing management
- 👤 Professional profile creation
- 🔍 Advanced search and discovery
- 📊 User dashboard with real-time stats
- 📸 Image upload support
- 🌓 Dark/Light theme toggle
- 📱 Fully mobile-responsive design
- 🎨 Modern UI with Tailwind CSS

## Tech Stack

- **Backend:** FastAPI (Python 3.11+)
- **Database:** SQLite (default, local dev) or PostgreSQL (production) with SQLAlchemy (async)
- **Authentication:** OAuth 2.0 (Google & Microsoft)
- **Frontend:** Jinja2 templates with Tailwind CSS
- **Deployment:** Railway

## Quick Start (All Setup Done!)

### ✅ Already Completed:
- Dependencies installed
- Environment configured
- Code verified
- Helper scripts created

### 🚀 Start Now:

```bash
# Option 1: Simple start
python run.py

# Option 2: Smart start (with checks)
python start_app.py

# Option 3: Check first
python quick_start.py
python run.py
```

**Then open:** http://localhost:8000

### 📝 Optional Configuration:

1. **Setup OAuth** (for login):
   ```bash
   python oauth_setup_guide.py
   # Add credentials to .env
   ```

2. **Setup Database** (optional):
   ```bash
   # SQLite is used by default (no setup needed!)
   # Database created automatically on first run
   # Or initialize manually:
   python init_database.py
   ```

**Note:** App works without OAuth/database - you can test UI immediately!

## Configuration

Set these environment variables in `.env`:

- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - Secret key for JWT tokens
- `GOOGLE_CLIENT_ID` & `GOOGLE_CLIENT_SECRET` - Google OAuth credentials
- `MICROSOFT_CLIENT_ID` & `MICROSOFT_CLIENT_SECRET` - Microsoft OAuth credentials
- `BASE_URL` - Base URL for OAuth redirects

## 🚀 Deployment to Railway

### Prerequisites
1. GitHub account
2. Railway account (https://railway.app)
3. Git installed on your computer

### Step 1: Push to GitHub

1. **Install Git** (if not already installed):
   - Download from: https://git-scm.com/downloads
   - Install and restart your terminal

2. **Initialize Git repository:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit - ConnectHub"
   ```

3. **Create GitHub repository:**
   - Go to https://github.com/new
   - Repository name: `connecthub`
   - Keep it public or private
   - Don't initialize with README (already exists)
   - Click "Create repository"

4. **Push to GitHub:**
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/connecthub.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Deploy on Railway

1. **Go to Railway:**
   - Visit https://railway.app
   - Sign up or log in with GitHub

2. **Create New Project:**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your `connecthub` repository

3. **Add PostgreSQL Database:**
   - Click "+ New"
   - Select "Database" → "PostgreSQL"
   - Railway will auto-provision a database

4. **Configure Environment Variables:**
   Click on your service → Variables tab, add:
   ```
   SECRET_KEY=your_secret_key_here_make_it_random_and_long
   BASE_URL=https://your-app.railway.app
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   ```
   
   Note: Railway automatically provides `DATABASE_URL` from PostgreSQL service

5. **Deploy:**
   - Railway automatically deploys when you push to GitHub
   - Check deployment logs in Railway dashboard
   - Your app will be live at: `https://your-app.railway.app`

### Step 3: Update Google OAuth Redirect URI

After deployment:
1. Go to Google Cloud Console
2. Update authorized redirect URIs:
   - Add: `https://your-app.railway.app/auth/google/callback`
3. Save changes

### Automatic Deployments

Once set up, every push to `main` branch automatically deploys to Railway! 🎉

### Troubleshooting

- **Build fails:** Check Railway logs for errors
- **Database connection fails:** Verify `DATABASE_URL` is set correctly
- **OAuth not working:** Update redirect URIs in Google/Microsoft console

## Project Structure

```
connecthub/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── config.py            # Configuration
│   ├── database.py          # Database setup
│   ├── models.py            # SQLAlchemy models
│   ├── routes/              # Route handlers
│   ├── templates/           # Jinja2 templates
│   └── static/              # Static files
├── requirements.txt
├── .env.example
└── README.md
```

## License

MIT

