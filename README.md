# E-Ink Imageserver (beta)
A flexible, self-hosted Flask web application designed to manage and serve images to multiple E-Ink photo frames. This server allows for centralized control over what images are displayed, when frames update, and how images are processed for different types of e-paper displays.

It's built to be the "brain" of a distributed digital art or photo frame system, perfect for home automation enthusiasts, digital artists, or anyone looking to create a dynamic, low-power display network.

Core Features
🖼️ Web-Based Management: An easy-to-use web interface to add, edit, and manage all your photo frames, image categories, screen types, and events.

📂 Flexible Image Sourcing: Indexes images from both a local directory (local_images) and a mounted network share (shared_images), allowing for easy integration with a NAS or shared file server.

🗂️ Dynamic Image Categories: Group images into categories by linking one or more image folders. Frames can be assigned to a category to control their content pool.

🗓️ Time-Based Event Scheduling: Create events (e.g., "Christmas," "Birthday") that automatically switch the content and update schedule for specific frames on certain dates.

🔌 External Event Triggers: Activate or deactivate "External Events" via simple HTTP GET requests. This allows seamless integration with home automation platforms like Home Assistant, Node-RED, or IFTTT.

⚙️ Automatic Image Processing: A scheduled background task automatically selects an appropriate image and runs a custom Python script to process it (e.g., resize, crop, dither) for the target e-ink display. The processed file is then ready for the frame to download.

📺 Extensible Screen Type Support: Easily add new e-ink screen types by providing a new image processing script. The server supports different orientations (horizontal, vertical) for each screen.

⚡ Efficient Caching: The image folder structure is cached to a JSON file for fast lookups, with a manual refresh option in the UI.

# How It Works
The server and frames operate in a coordinated, pull-based system:

-Configuration: You use the web UI to configure your Photo Frames (giving them an ID and IP), upload images, create Categories, and set up Events.

-Scheduled Processing: Every hour, a background task on the server checks for frames that have a scheduled wake-up time in the upcoming hour.

-Image Selection & Processing: For each due frame, the server:

-Identifies the frame's assigned Category.

-Picks a random, orientation-appropriate image from the folders linked to that category.

-Executes the Python script associated with the frame's Screen Type (e.g., 6color73i.py), passing it the chosen image.

-The script processes the image (resizes, dithers) and saves the output as a device-ready file (e.g., a .h C-header file named static/frameABC.h).

-Frame Wake-Up & Fetch: The physical E-Ink frame (e.g., an ESP32 device) wakes up at its scheduled time. It connects to the network and makes two requests to the server:

-It downloads its updated wake-up schedule from a unique URL (e.g., http://server-ip/static/frameABC.txt).

-It downloads the pre-processed image data from its unique URL (e.g., http://server-ip/static/frameABC.h).

-Display & Sleep: The frame displays the new image and goes back to deep sleep until the next scheduled wake-up time.


# INSTALLATION:

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


# First Run
Run the application directly with Flask for the first time. This will create the imageserver.db SQLite database file with the necessary tables.

Bash

# Make sure you are in the venv (source venv/bin/activate)
python app.py
Once you see it running, you can stop it with Ctrl+C. The database is now initialized.



Deployment for Production (using Gunicorn)
Using the built-in Flask server is not suitable for production. Gunicorn is a robust WSGI server that can run the application reliably. The included imageserver.wsgi file is the entry point for Gunicorn.

To run the server with Gunicorn:


# Navigate to the parent directory of your app
cd /home/dietpi/imageserver

# Run Gunicorn, binding to all network interfaces on port 8000
# The command is `gunicorn [options] {module_name}:{application_variable_name}`
gunicorn --bind 0.0.0.0:8000 imageserver:application --daemon
--bind 0.0.0.0:8000: Makes the server accessible on your local network at port 8000.

--daemon: Runs the process in the background.

imageserver:application: Tells Gunicorn to look inside the imageserver.wsgi file for the Flask app instance named application.

You should now be able to access the web interface at http://<your-server-ip>:8000.

To make the server start automatically on boot, it's recommended to create a systemd service file.
