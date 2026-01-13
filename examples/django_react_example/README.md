# Django + React + Clerk Example

A minimal example demonstrating how to use `django-clerk-users` with a React frontend.

## What This Demonstrates

- **JWT Authentication**: React sends Clerk JWT tokens to Django
- **Session Optimization**: Django validates JWT once, then uses session
- **Protected Endpoints**: Using `@clerk_user_required` decorator
- **Webhook Handling**: Endpoint for Clerk webhooks

## Prerequisites

- Python 3.12+
- Node.js 20+
- A [Clerk](https://clerk.com) account with an application

## Quick Start with rav

From the repository root:

```bash
# Install rav if you don't have it
pip install rav

# Install dependencies
rav run examples:setup

# Run migrations
rav run examples:backend:migrate

# Terminal 1 - Run backend
rav run examples:backend

# Terminal 2 - Run frontend
rav run examples:frontend
```

## Manual Setup

### 1. Get Clerk API Keys

From [Clerk Dashboard](https://dashboard.clerk.com):

- **Publishable Key** (starts with `pk_test_`)
- **Secret Key** (starts with `sk_test_`)
- **Webhook Signing Secret** (optional, starts with `whsec_`)

### 2. Backend Setup

```bash
cd backend

# Create .env file
cp .env.example .env
# Edit .env with your CLERK_SECRET_KEY

# Install dependencies
pip install django django-cors-headers python-dotenv django-clerk-users

# Run migrations
python manage.py migrate

# Start server
python manage.py runserver
```

### 3. Frontend Setup

```bash
cd frontend

# Create .env file
cp .env.example .env
# Edit .env with your VITE_CLERK_PUBLISHABLE_KEY

# Install dependencies
npm install

# Start dev server
npm run dev
```

### 4. Configure Clerk Dashboard

In your Clerk application settings:

1. Add `http://localhost:5173` to **Allowed Origins**
2. (Optional) Set up webhook endpoint: `http://localhost:8000/webhooks/clerk/`

## Usage

1. Open http://localhost:5173
2. Sign in with Clerk
3. Click the API buttons to test authenticated requests

## API Endpoints

| Endpoint | Auth Required | Description |
|----------|---------------|-------------|
| `GET /api/public/` | No | Shows auth status |
| `GET /api/protected/` | Yes | Protected resource |
| `GET /api/profile/` | Yes | User profile data |
| `POST /webhooks/clerk/` | Signature | Clerk webhook events |

## Project Structure

```
backend/
├── backend/
│   ├── settings.py    # Django + Clerk config
│   └── urls.py        # URL routing
└── api/
    ├── views.py       # Example API views
    └── urls.py        # API routes

frontend/
└── src/
    ├── main.jsx       # ClerkProvider setup
    └── App.jsx        # UI with API calls
```

## Key Code

### Django Settings (backend/backend/settings.py)

```python
INSTALLED_APPS = [
    ...
    "django_clerk_users",
]

MIDDLEWARE = [
    ...
    "django_clerk_users.middleware.ClerkAuthMiddleware",
]

AUTH_USER_MODEL = "django_clerk_users.ClerkUser"
CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY")
CLERK_FRONTEND_HOSTS = ["http://localhost:5173"]
```

### Protected View (backend/api/views.py)

```python
from django_clerk_users.decorators import clerk_user_required

@clerk_user_required
def protected_view(request):
    user = request.clerk_user
    return JsonResponse({"email": user.email})
```

### React Auth (frontend/src/App.jsx)

```jsx
const { getToken } = useAuth()

const response = await fetch('/api/protected/', {
  headers: {
    Authorization: `Bearer ${await getToken()}`,
  },
})
```
