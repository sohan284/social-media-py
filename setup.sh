#!/bin/bash

echo "🚀 Social Media DRF Setup Script"
echo "=================================="

# Check Python version
echo "📌 Checking Python version..."
python3 --version

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "⚠️  Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check Redis
echo ""
echo "🔍 Checking Redis..."
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is running"
else
    echo "⚠️  Redis is not running. Please start Redis:"
    echo "   macOS: brew services start redis"
    echo "   Linux: sudo systemctl start redis"
fi

# Run migrations
echo ""
echo "🗄️  Running database migrations..."
python manage.py makemigrations
python manage.py migrate

# Collect static files
echo ""
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Create superuser: python manage.py createsuperuser"
echo "   2. Start server: daphne -b 0.0.0.0 -p 8000 app.asgi:application"
echo "   3. Or use: python manage.py runserver"
echo ""
echo "🌐 Access points:"
echo "   - Admin: http://localhost:8000/admin/"
echo "   - Swagger: http://localhost:8000/swagger/"
echo "   - API: http://localhost:8000/api/"


