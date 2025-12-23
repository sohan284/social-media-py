# Social Media DRF API

এটি একটি Django REST Framework ভিত্তিক Social Media API প্রজেক্ট।

## প্রজেক্ট সেটআপ (Setup Instructions)

### 1. Python Virtual Environment তৈরি করুন

```bash
# Python 3.8+ প্রয়োজন
python3 -m venv venv

# Virtual environment activate করুন
# macOS/Linux:
source venv/bin/activate

# Windows:
# venv\Scripts\activate
```

### 2. Dependencies ইনস্টল করুন

```bash
pip install -r requirements.txt
```

### 3. Redis ইনস্টল করুন (WebSocket/Chat এর জন্য)

**macOS:**
```bash
brew install redis
brew services start redis
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**Windows:**
- Redis Windows version ডাউনলোড করুন: https://github.com/microsoftarchive/redis/releases
- অথবা WSL2 ব্যবহার করুন

### 4. Database Migration করুন

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Superuser তৈরি করুন (Admin Panel এর জন্য)

```bash
python manage.py createsuperuser
```

### 6. Static Files Collect করুন

```bash
python manage.py collectstatic --noinput
```

### 7. Server চালু করুন

```bash
# Daphne ব্যবহার করুন (WebSocket support এর জন্য)
daphne -b 0.0.0.0 -p 8000 app.asgi:application

# অথবা সাধারণ Django development server:
python manage.py runserver
```

## API Endpoints

- **Admin Panel:** http://localhost:8000/admin/
- **Swagger Documentation:** http://localhost:8000/swagger/
- **ReDoc Documentation:** http://localhost:8000/redoc/
- **API Base:** http://localhost:8000/api/
- **Auth Endpoints:** http://localhost:8000/auth/

## Features

- ✅ User Authentication (JWT)
- ✅ Social Login (Google, Apple)
- ✅ Posts Management
- ✅ Comments & Likes
- ✅ Community/Group Features
- ✅ Real-time Chat (WebSocket)
- ✅ Marketplace
- ✅ Interest Categories
- ✅ Notifications
- ✅ Follow/Unfollow

## Important Notes

1. **Redis** চালু থাকতে হবে WebSocket/Chat feature এর জন্য
2. **SECRET_KEY** production এ পরিবর্তন করুন
3. **EMAIL_HOST_PASSWORD** আপনার Gmail App Password দিয়ে পরিবর্তন করুন
4. Database SQLite ব্যবহার করছে (development), production এ PostgreSQL ব্যবহার করুন

## Troubleshooting

### Redis Connection Error
```bash
# Redis চালু আছে কিনা check করুন
redis-cli ping
# Response: PONG হলে Redis চালু আছে
```

### Migration Issues
```bash
# সব migrations reset করতে:
python manage.py migrate --run-syncdb
```

### Port Already in Use
```bash
# অন্য port ব্যবহার করুন:
daphne -b 0.0.0.0 -p 8001 app.asgi:application
```


