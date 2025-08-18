# Telegram PDF→TIFF Конвертер Бот

Минималистичный Telegram-бот для конвертации PDF документов в TIFF файлы с параметрами:
- Сжатие: LZW
- Цветовое пространство: CMYK  
- Разрешение: 96 DPI
- Автодеплой с GitHub Actions

## 🚀 Быстрый старт

### 1. Подготовка VPS

```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем Docker и Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo apt install docker-compose-plugin

# Создаем пользователя для бота
sudo useradd -m -s /bin/bash botuser
sudo usermod -aG docker botuser

# Создаем директории
sudo mkdir -p /srv/files
sudo chown botuser:botuser /srv/files
sudo mkdir -p /tmp/bot
sudo chown botuser:botuser /tmp/bot
```

### 2. Установка ImageMagick и зависимостей

```bash
# Устанавливаем ImageMagick и профили
sudo apt install -y imagemagick ghostscript icc-profiles nginx

# Настраиваем политику ImageMagick (разрешаем PDF)
sudo nano /etc/ImageMagick-6/policy.xml
```

Найдите строки с PDF и закомментируйте/удалите их:
```xml
<!-- <policy domain="coder" rights="none" pattern="PDF" /> -->
```

### 3. Клонирование и настройка

```bash
# Переходим под пользователя бота
sudo su - botuser

# Клонируем репозиторий
git clone https://github.com/yourusername/telegram-pdf-tiff-bot.git
cd telegram-pdf-tiff-bot

# Копируем и настраиваем переменные окружения
cp .env.example .env
nano .env
```

Настройте `.env`:
```env
BOT_TOKEN=your_bot_token_from_botfather
PUBLIC_BASE_URL=https://your-domain.com
PUBLISH_DIR=/srv/files
TMP_DIR=/tmp/bot
MAX_FILE_MB=100
IMAGEMAGICK_PATH=/usr/bin/convert
ICC_CMYK_PROFILE=/usr/share/color/icc/CMYK.icc
CONCURRENCY=2
```

### 4. Настройка Nginx

```bash
# Копируем конфигурацию nginx
sudo cp config/nginx.conf /etc/nginx/sites-available/pdf-tiff-bot
sudo ln -s /etc/nginx/sites-available/pdf-tiff-bot /etc/nginx/sites-enabled/

# Удаляем дефолтный сайт
sudo rm /etc/nginx/sites-enabled/default

# Перезагружаем nginx
sudo systemctl reload nginx
```

### 5. Запуск через Docker Compose

```bash
# Сборка и запуск
docker compose up -d --build

# Проверяем логи
docker compose logs -f bot
```

## 🔧 GitHub Actions Автодеплой

### 1. Настройка SSH

На VPS:
```bash
# Генерируем SSH ключи
ssh-keygen -t rsa -b 4096 -f ~/.ssh/github_deploy
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/github_deploy  # Копируем приватный ключ
```

### 2. Настройка секретов в GitHub

В настройках репозитория добавьте секреты:
- `VPS_SSH_KEY` - приватный SSH ключ
- `VPS_HOST` - IP или домен VPS
- `VPS_USERNAME` - имя пользователя (botuser)

### 3. Автодеплой

При каждом push в ветку `main` бот автоматически пересобирается и перезапускается на VPS.

## 📋 Команды управления

```bash
# Просмотр логов
docker compose logs -f bot

# Перезапуск
docker compose restart

# Остановка
docker compose down

# Обновление и перезапуск
git pull && docker compose up -d --build

# Проверка статуса nginx
sudo systemctl status nginx

# Перезагрузка nginx
sudo systemctl reload nginx
```

## 🔒 Безопасность

### Настройки ImageMagick
Проверьте `/etc/ImageMagick-6/policy.xml`:
```xml
<!-- Разрешаем PDF, но ограничиваем ресурсы -->
<policy domain="resource" name="memory" value="256MiB"/>
<policy domain="resource" name="map" value="512MiB"/>
<policy domain="resource" name="width" value="16KP"/>
<policy domain="resource" name="height" value="16KP"/>
<policy domain="resource" name="disk" value="1GiB"/>
```

### Файрволл
```bash
sudo ufw allow 22   # SSH
sudo ufw allow 80   # HTTP
sudo ufw allow 443  # HTTPS (если используете SSL)
sudo ufw enable
```

## 🐛 Устранение неполадок

### Проблемы с ImageMagick
```bash
# Проверка версии
convert -version

# Тест конвертации
convert -density 96 test.pdf -colorspace CMYK -compress LZW test.tiff

# Проверка политик
convert -list policy
```

### Проблемы с правами доступа
```bash
# Проверяем права
ls -la /srv/files
ls -la /tmp/bot

# Исправляем при необходимости
sudo chown -R botuser:botuser /srv/files /tmp/bot
```

### Проблемы с Docker
```bash
# Проверка статуса
docker compose ps

# Перезапуск с очисткой
docker compose down -v
docker compose up -d --build

# Проверка образов
docker images
```

## 📊 Мониторинг

### Логи бота
```bash
# Реальное время
docker compose logs -f bot

# Последние строки
docker compose logs --tail 100 bot
```

### Логи Nginx
```bash
sudo tail -f /var/log/nginx/pdf-tiff-bot.access.log
sudo tail -f /var/log/nginx/pdf-tiff-bot.error.log
```

### Использование дисковой памяти
```bash
# Размер публичной директории
du -sh /srv/files

# Временные файлы
du -sh /tmp/bot
```

## ⚙️ Настройка SSL (опционально)

### Certbot для Let's Encrypt
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Обновление nginx.conf для HTTPS
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    location /files {
        alias /srv/files/;
        autoindex off;
        try_files $uri =404;
    }
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

## 🧪 Тестирование

### Тестовые файлы
1. Простой PDF (1 страница)
2. Многостраничный PDF
3. Большой файл (близко к лимиту)
4. Файл неправильного формата

### Проверка результата
```bash
# Информация о TIFF файле
identify -verbose /srv/files/output.tiff

# Проверка цветового пространства
identify -format "%[colorspace]" /srv/files/output.tiff
```

## 📈 Масштабирование

### Увеличение производительности
- Увеличьте `CONCURRENCY` в `.env`
- Добавьте больше RAM и CPU на VPS
- Настройте SSD для быстрого I/O

### Мониторинг ресурсов
```bash
# Использование CPU и памяти
htop

# Дисковое пространство
df -h

# Сетевая активность
iftop
```

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи бота и nginx
2. Убедитесь в корректности настроек `.env`
3. Проверьте права доступа к файлам
4. Проверьте статус всех сервисов

---

**Версия:** 1.0  
**Лицензия:** MIT  
**Автор:** Telegram PDF-TIFF Bot