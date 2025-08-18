#!/bin/bash
# Скрипт быстрой установки для VPS

set -e

echo "🚀 Установка Telegram PDF→TIFF Bot..."

# Проверяем, что скрипт запущен с правами sudo
if [[ $EUID -eq 0 ]]; then
   echo "❌ Не запускайте этот скрипт от root! Используйте sudo для отдельных команд."
   exit 1
fi

# Обновляем систему
echo "📦 Обновление системы..."
sudo apt update && sudo apt upgrade -y

# Устанавливаем Docker
echo "🐳 Установка Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
fi

# Устанавливаем Docker Compose
echo "🔧 Установка Docker Compose..."
sudo apt install -y docker-compose-plugin

# Устанавливаем системные зависимости
echo "📚 Установка зависимостей..."
sudo apt install -y imagemagick ghostscript icc-profiles nginx git

# Создаем пользователя для бота
echo "👤 Создание пользователя botuser..."
if ! id "botuser" &>/dev/null; then
    sudo useradd -m -s /bin/bash botuser
    sudo usermod -aG docker botuser
fi

# Создаем директории
echo "📁 Создание директорий..."
sudo mkdir -p /srv/files /tmp/bot
sudo chown botuser:botuser /srv/files /tmp/bot

# Настраиваем политику ImageMagick
echo "🖼️ Настройка ImageMagick политики..."
sudo sed -i 's/<policy domain="coder" rights="none" pattern="PDF" \/>$/<!-- <policy domain="coder" rights="none" pattern="PDF" \/> -->/' /etc/ImageMagick-6/policy.xml 2>/dev/null || true

# Запрашиваем токен бота
echo ""
echo "🤖 Настройка Telegram бота..."
read -p "Введите токен бота от BotFather: " BOT_TOKEN
read -p "Введите домен или IP адрес (например, https://example.com): " PUBLIC_URL

# Клонируем репозиторий
echo "📥 Клонирование репозитория..."
sudo -u botuser git clone https://github.com/yourusername/telegram-pdf-tiff-bot.git /home/botuser/telegram-pdf-tiff-bot

# Создаем .env файл
echo "⚙️ Создание конфигурации..."
sudo -u botuser tee /home/botuser/telegram-pdf-tiff-bot/.env > /dev/null <<EOF
BOT_TOKEN=$BOT_TOKEN
PUBLIC_BASE_URL=$PUBLIC_URL
PUBLISH_DIR=/srv/files
TMP_DIR=/tmp/bot
MAX_FILE_MB=100
IMAGEMAGICK_PATH=/usr/bin/convert
ICC_CMYK_PROFILE=/usr/share/color/icc/CMYK.icc
CONCURRENCY=2
EOF

# Настраиваем nginx
echo "🌐 Настройка Nginx..."
sudo cp /home/botuser/telegram-pdf-tiff-bot/config/nginx.conf /etc/nginx/sites-available/pdf-tiff-bot
sudo ln -sf /etc/nginx/sites-available/pdf-tiff-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Запускаем бота
echo "🚀 Запуск бота..."
cd /home/botuser/telegram-pdf-tiff-bot
sudo -u botuser docker compose up -d --build

# Проверяем статус
sleep 5
if sudo -u botuser docker compose ps | grep -q "Up"; then
    echo ""
    echo "✅ Установка завершена успешно!"
    echo "🔗 Файлы будут доступны по адресу: $PUBLIC_URL/files/"
    echo "📋 Управление ботом: cd /home/botuser/telegram-pdf-tiff-bot && docker compose logs -f"
    echo ""
    echo "📝 Для автодеплоя настройте GitHub Actions с секретами:"
    echo "   VPS_SSH_KEY, VPS_HOST, VPS_USERNAME"
else
    echo "❌ Что-то пошло не так. Проверьте логи: cd /home/botuser/telegram-pdf-tiff-bot && docker compose logs"
fi