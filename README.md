# AI Smart Assistant

AI Smart Assistant is a full-stack web application with:

- Flask backend APIs
- static HTML/CSS/JS frontend
- MongoDB for persistence
- JWT authentication with refresh sessions
- Gemini-powered text responses
- group chat and image features

The backend serves frontend files directly, so this project can run as one deployable service.

## Project Structure

frontend/
- HTML pages and static assets
- JavaScript client logic

backend/
- Flask app entry point and routes
- database models and middleware
- AI service integration
- uploaded files

## Features

- Email/password auth with refresh token sessions
- Personal chat history with search and pin support
- Private group chat with invite links
- Document upload and extraction for context
- AI image generation endpoint with fallback handling
- Realtime updates using Socket.IO
- Light/dark themes and responsive UI

## Requirements

- Python 3.10+
- MongoDB (Atlas recommended for production)
- Gemini API key

## Local Setup

1. Clone repository

2. Create virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install backend dependencies

```powershell
cd backend
pip install -r requirements.txt
```

4. Create backend/.env with required values

```env
GEMINI_API_KEY=your_gemini_api_key
MONGODB_URI=your_mongodb_connection_string
DB_NAME=ai_assistant
JWT_SECRET_KEY=your_long_random_jwt_secret
FLASK_SECRET_KEY=your_long_random_flask_secret
FLASK_ENV=development
PORT=5000
```

5. Run the app

```powershell
python app.py
```

6. Open in browser

http://localhost:5000

## Where To Host Frontend

Recommended: host frontend and backend together on one service.

Reason:
- backend/app.py already serves frontend static files
- no separate frontend build pipeline is required
- avoids cross-origin and API URL mismatch issues

Best option for this repo:
- Render Web Service for backend + frontend
- MongoDB Atlas for database

## Production Deployment (Render)

1. Push code to GitHub

2. Create a MongoDB Atlas cluster and get connection URI

3. In Render, create a new Web Service from the repo

4. Configure service:
- Root Directory: backend
- Build Command: pip install -r requirements.txt
- Start Command: python app.py

5. Add environment variables in Render:
- GEMINI_API_KEY
- MONGODB_URI
- DB_NAME
- JWT_SECRET_KEY
- FLASK_SECRET_KEY
- FLASK_ENV=production

6. Deploy and open the service URL

## Optional: Separate Frontend Hosting

If you host frontend separately (for example Netlify or Vercel), update API base URL in [frontend/js/chat.js](frontend/js/chat.js) to point to your backend domain.

Current code uses a hardcoded localhost URL for development, so this must be changed for split hosting.

## Common Production Notes

- Set strong random values for JWT_SECRET_KEY and FLASK_SECRET_KEY
- Use MongoDB Atlas network and user access rules correctly
- Restrict CORS to your frontend domain in production
- Monitor backend logs for provider errors and failed requests

## Troubleshooting

500 errors on image generation:
- check backend logs for provider details
- verify outbound internet access from hosting platform

Login not working:
- verify JWT_SECRET_KEY is set
- verify MongoDB URI and DB_NAME

Frontend cannot reach API:
- verify frontend API base URL
- verify backend URL and CORS settings

## License

Add your preferred license here.