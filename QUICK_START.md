# 🚀 Quick Start Guide (দ্রুত শুরু করার গাইড)

## Step 1: Virtual Environment তৈরি করুন

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
```

## Step 2: Dependencies ইনস্টল করুন

```bash
pip install -r requirements.txt
```

## Step 3: Redis চালু করুন

```bash
# macOS:
brew install redis
brew services start redis

# Check করুন:
redis-cli ping  # "PONG" response আসবে
```

## Step 4: Database Setup করুন

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # Admin user তৈরি করুন
```

## Step 5: Server চালু করুন

```bash
# Option 1: Daphne (WebSocket support সহ - Recommended)
daphne -b 0.0.0.0 -p 8000 app.asgi:application

# Option 2: Django Development Server
python manage.py runserver
```

## ✅ সব কিছু ঠিক আছে কিনা Check করুন

1. **Admin Panel:** http://localhost:8000/admin/ - Login করুন
2. **Swagger Docs:** http://localhost:8000/swagger/ - API documentation দেখুন
3. **API Test:** http://localhost:8000/api/ - API endpoints test করুন

## 🔧 Common Issues & Solutions

### Issue: Redis connection error
**Solution:** Redis চালু করুন
```bash
brew services start redis  # macOS
sudo systemctl start redis  # Linux
```

### Issue: Port 8000 already in use
**Solution:** অন্য port ব্যবহার করুন
```bash
daphne -b 0.0.0.0 -p 8001 app.asgi:application
```

### Issue: Migration errors
**Solution:** Database reset করুন (⚠️ সব data delete হবে)
```bash
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

## 📝 Important Files

- `app/settings.py` - Main configuration
- `requirements.txt` - Python packages
- `app/urls.py` - URL routing
- `accounts/` - User authentication
- `post/` - Posts & Comments
- `chats/` - Real-time messaging
- `community/` - Groups/Communities
- `marketplace/` - E-commerce features

## 🎯 Next Steps

1. ✅ Server চালু করুন
2. ✅ Admin panel এ login করুন
3. ✅ Swagger documentation দেখুন
4. ✅ API endpoints test করুন
5. ✅ Frontend connect করুন


