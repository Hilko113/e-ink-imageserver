# imageserver
E-ink ImageServer


Install DietPi

In DietPi Menu install Python and Apache.

```
sudo apt install libapache2-mod-wsgi-py3
sudo pip3 install Flask
mkdir imageserver
cd imageserver
nano app.py
cd /etc/apache2/sites-available
```
```
sudo nano /etc/apache2/sites-available/imageserver.conf
```
Paste the text below:
```
<VirtualHost 192.168.2.100:80>
    ServerName 192.168.2.100

    # Set up the WSGI process
    WSGIDaemonProcess imageserver user=www-data group=www-data threads=5
    WSGIScriptAlias / /home/dietpi/imageserver/imageserver.wsgi

    # Set permissions for the project directory
    <Directory /home/dietpi/imageserver>
        Require all granted
    </Directory>

    # Configure static files
    Alias /static /home/dietpi/imageserver/static
    <Directory /home/dietpi/imageserver/static/>
        Require all granted
    </Directory>

    # Error and access log files
    ErrorLog ${APACHE_LOG_DIR}/imageserver_error.log
    CustomLog ${APACHE_LOG_DIR}/imageserver_access.log combined
</VirtualHost>
```
```
cd /home/dietpi/imageserver
```
```
sudo nano /home/dietpi/imageserver/imageserver.wsgi
```
Paste the text below:
```
import sys
sys.path.insert(0, "/home/dietpi/imageserver")

from app import app as application
```

```
sudo a2ensite imageserver
sudo systemctl restart apache2
sudo chown -R www-data:www-data /home/dietpi/imageserver
sudo chmod -R 755 /home/dietpi/imageserver
sudo pip3 install SQLAlchemy
sudo pip3 install Flask-SQLAlchemy
sudo pip install pillow
```


How to mount a network share:
```
sudo apt install cifs-utils
sudo mkdir /home/dietpi/imageserver/shared_images
sudo mount.cifs //192.168.1.1/pictures /home/dietpi/imageserver/shared_images -o username=YOURUSERNAME,password=YOURPASSWORD
```
Add mounting to startup:
```
sudo nano /etc/fstab
//192.168.1.1/pictures /home/dietpi/imageserver/shared_images cifs username=YOURUSERNAME,password=YOURPASSWORD,iocharset=utf8,vers=3.0 0 0
```
