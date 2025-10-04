from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, request, redirect, url_for, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
import os
import re
import json
import time
import threading  # Import threading module
import random
import subprocess
from PIL import Image

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Path to the mounted shared folder
SHARED_IMAGES_PATH = '/home/dietpi/imageserver/shared_images'
LOCAL_IMAGES_PATH = '/home/dietpi/imageserver/local_images'
# Cache file path
CACHE_FILE_PATH = '/home/dietpi/imageserver/image_cache.json'
# Cache duration (24 hours)
CACHE_DURATION = 24 * 60 * 60  # in seconds (24 hours)

SHARED_IMAGES_BASE = SHARED_IMAGES_PATH
LOCAL_IMAGES_BASE = LOCAL_IMAGES_PATH

# Define the path to the static folder
STATIC_FOLDER_PATH = os.path.join(os.path.dirname(__file__), 'static')

# Database configuration
db_path = os.path.join(os.path.dirname(__file__), 'imageserver.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Association table for many-to-many relationship between events and frames
event_frame_association = db.Table('event_frame',
    db.Column('event_id', db.Integer, db.ForeignKey('event.id'), primary_key=True),
    db.Column('frame_id', db.Integer, db.ForeignKey('photo_frame.id'), primary_key=True)
)

# Update the Event model to include a relationship with PhotoFrame
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    start_day_month = db.Column(db.String(5), nullable=False)  # Format: MM-DD
    end_day_month = db.Column(db.String(5), nullable=True)     # Format: MM-DD
    event_times = db.Column(db.String(100), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    category = db.relationship('Category', backref='events')
    frames = db.relationship('PhotoFrame', secondary=event_frame_association, backref='events')

# Association table for many-to-many relationship between external events and frames
external_event_frame_association = db.Table('external_event_frame',
    db.Column('external_event_id', db.Integer, db.ForeignKey('external_event.id'), primary_key=True),
    db.Column('frame_id', db.Integer, db.ForeignKey('photo_frame.id'), primary_key=True)
)

# Define the ExternalEvent model
class ExternalEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    linkname = db.Column(db.String(50), unique=True, nullable=False)
    event_times = db.Column(db.String(100), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    category = db.relationship('Category', backref='external_events')
    frames = db.relationship('PhotoFrame', secondary=external_event_frame_association, backref='external_events')

# Define the Category model
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    linked_folders = db.Column(db.String(255), nullable=False)  # Comma-separated folder names

# Update the PhotoFrame model to include a foreign key to Category
class PhotoFrame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_code = db.Column(db.String(3), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(15), nullable=False)
    wake_up_times = db.Column(db.String(100), nullable=True)
    active_wake_up_times = db.Column(db.String(100), nullable=True)
    screen_type = db.Column(db.String(50), db.ForeignKey('screen_type.name'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)  # Link to Category
    category = db.relationship('Category', backref='photo_frames')

# Define the ScreenType model
class ScreenType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    script_filename = db.Column(db.String(100), nullable=False)
    orientation = db.Column(db.String(10), nullable=False)  # New field for orientation

# Create the database tables if they don't exist and add the default screen type
with app.app_context():
    db.create_all()
    if not ScreenType.query.filter_by(name="6 Color Spectra 7.3 inch Horizontal").first():
        default_screen = ScreenType(name="6 Color Spectra 7.3 inch Horizontal", script_filename="6color73i.py", orientation="Horizontal")
        db.session.add(default_screen)

    # Ensure default category exists with "Local - default" folder
    if not Category.query.filter_by(name="default").first():
        default_category = Category(name="default", linked_folders="Local - default")
        db.session.add(default_category)
    
    db.session.commit()

# Function to determine if an event is active based on today's date
def is_event_active(event, current_date):
    current_month = current_date.month
    current_day = current_date.day

    # Extract event start month and day
    event_start_month, event_start_day = map(int, event.start_day_month.split('-'))

    # Check if today's date matches the event's start date
    return current_month == event_start_month and current_day == event_start_day

# Function to determine if an event should end based on today's date
def is_event_not_active(event, current_date):
    current_month = current_date.month
    current_day = current_date.day

    # Extract event end month and day
    event_end_month, event_end_day = map(int, event.end_day_month.split('-'))

    # Check if today's date matches the event's end date
    return current_month == event_end_month and current_day == event_end_day

# Function to check events and update photo frames
def check_events():
    while True:
        with app.app_context():
            current_date = datetime.now()
            events = Event.query.all()
            for event in events:
                if is_event_active(event, current_date):
                    # Event is active
                    for frame in event.frames:
                        frame.category_id = event.category_id
                        frame.active_wake_up_times = event.event_times  # Set wake-up times if applicable
                        db.session.add(frame)  # Track changes to the frame
                        
                        # Write updated active wake-up times to the corresponding file
                        write_wake_up_times_to_file(frame.id_code, frame.active_wake_up_times)
                    db.session.commit()
                
                elif is_event_not_active(event, current_date):
                    # Event is ending today
                    for frame in event.frames:
                        frame.category_id = None  # Or set to a default category ID
                        frame.active_wake_up_times = frame.wake_up_times  # Reset to default wake-up times
                        db.session.add(frame)  # Track changes to the frame
                        
                        # Write reset wake-up times to the file
                        write_wake_up_times_to_file(frame.id_code, frame.active_wake_up_times)
                    db.session.commit()

        # Sleep for 10 minutes
        time.sleep(150)  # 150 seconds

# Start the background thread when the app starts
event_thread = threading.Thread(target=check_events)
event_thread.daemon = True  # Daemonize thread
event_thread.start()

def write_wake_up_times_to_file(frame_id, active_wake_up_times):
    """Writes the active wake-up times to a text file named after the frame ID."""
    filename = f"frame{frame_id}.txt"
    file_path = os.path.join(STATIC_FOLDER_PATH, filename)
    
    # Ensure the static folder exists
    os.makedirs(STATIC_FOLDER_PATH, exist_ok=True)
    
    # Write the active wake-up times to the file
    with open(file_path, 'w') as file:
        file.write(active_wake_up_times or "")

def pick_random_image_from_category(category, orientation):
    # Load cached data from the JSON file
    with open(CACHE_FILE_PATH, 'r') as cache_file:
        folders = json.load(cache_file)
    
    image_paths = []
    linked_folders = category.linked_folders.split(',')

    for folder_name in linked_folders:
        folder_name = folder_name.strip()
        
        # Retrieve images from the cached data
        folder_images = folders.get(folder_name)
        if folder_images:
            for image_info in folder_images:
                # Include square images for both horizontal and vertical requests
                if (
                    image_info["orientation"].lower() == orientation.lower() or
                    (orientation.lower() in ["horizontal", "vertical"] and image_info["orientation"].lower() == "square")
                ):
                    # Construct the image path
                    image_path = os.path.join(
                        SHARED_IMAGES_BASE if folder_name.startswith("Shared - ") else LOCAL_IMAGES_BASE,
                        folder_name.split(" - ", 1)[1].strip(),
                        image_info["name"]
                    )
                    image_paths.append(image_path)

    # Shuffle the list of image paths to introduce randomness
    random.shuffle(image_paths)

    # Select the first image in the shuffled list, or None if no images are found
    return image_paths[0] if image_paths else None

# Helper function to validate ID code
def is_valid_id_code(id_code):
    return bool(re.match(r'^[A-Za-z0-9]{3}$', id_code))

@app.route('/')
def home():
    photo_frames = PhotoFrame.query.all()
    return render_template('home.html', photo_frames=photo_frames)

@app.route('/add_frame', methods=['GET', 'POST'])
def add_frame():
    if request.method == 'POST':
        id_code = request.form['id_code']
        name = request.form['name']
        ip_address = request.form['ip_address']
        wake_up_times = request.form['wake_up_times']
        active_wake_up_times = request.form['wake_up_times']
        screen_type = request.form['screen_type']
        category_id = request.form.get('category_id')

        # Create a new PhotoFrame
        new_frame = PhotoFrame(
            id_code=id_code,
            name=name,
            ip_address=ip_address,
            wake_up_times=wake_up_times,
            active_wake_up_times=active_wake_up_times,
            screen_type=screen_type,
            category_id=category_id
        )
        db.session.add(new_frame)
        db.session.commit()

        # Write active wake-up times to the file
        write_wake_up_times_to_file(id_code, active_wake_up_times)
        
        return redirect(url_for('home'))
    
    screen_types = ScreenType.query.all()
    categories = Category.query.all()
    return render_template('add_frame.html', screen_types=screen_types, categories=categories)

@app.route('/edit_frame/<int:id>', methods=['GET', 'POST'])
def edit_frame(id):
    photo_frame = PhotoFrame.query.get_or_404(id)
    screen_types = ScreenType.query.all()
    categories = Category.query.all()
    
    if request.method == 'POST':
        photo_frame.id_code = request.form['id_code']
        photo_frame.name = request.form['name']
        photo_frame.ip_address = request.form['ip_address']
        photo_frame.wake_up_times = request.form['wake_up_times']
        photo_frame.active_wake_up_times = request.form['wake_up_times']
        photo_frame.screen_type = request.form['screen_type']
        photo_frame.category_id = request.form.get('category_id')

        db.session.commit()
        
        # Write active wake-up times to the file
        write_wake_up_times_to_file(photo_frame.id_code, photo_frame.active_wake_up_times)
        
        return redirect(url_for('home'))

    return render_template('edit_frame.html', photo_frame=photo_frame, screen_types=screen_types, categories=categories)

# Delete photo frame
@app.route('/delete_frame/<int:id>', methods=['POST'])
def delete_frame(id):
    photo_frame = PhotoFrame.query.get_or_404(id)
    db.session.delete(photo_frame)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        name = request.form['name']
        script_filename = request.form['script_filename']
        orientation = request.form['orientation']  # Get orientation from the form
        
        # Check if screen type with the same name already exists
        if not ScreenType.query.filter_by(name=name).first():
            # Create and add the new screen type to the database
            new_screen_type = ScreenType(name=name, script_filename=script_filename, orientation=orientation)
            db.session.add(new_screen_type)
            db.session.commit()
    
    screen_types = ScreenType.query.all()
    return render_template('settings.html', screen_types=screen_types)

@app.route('/delete_screen_type/<string:name>', methods=['POST'])
def delete_screen_type(name):
    screen_type = ScreenType.query.filter_by(name=name).first()
    if screen_type:
        db.session.delete(screen_type)
        db.session.commit()
    
    return redirect(url_for('settings'))

@app.route('/events')
def events():
    # Fetch all events from the database
    events = Event.query.all()
    return render_template('events.html', events=events)

@app.route('/add_event', methods=['GET', 'POST'])
def add_event():
    categories = Category.query.all()
    frames = PhotoFrame.query.all()  # Fetch all frames for selection
    
    if request.method == 'POST':
        name = request.form['name']  # Capture the name field
        start_month = request.form['start_month']
        start_day = request.form['start_day']
        end_month = request.form['end_month']
        end_day = request.form['end_day']
        event_times = ','.join(request.form.getlist('event_time'))
        category_id = request.form.get('category_id')
        selected_frame_ids = request.form.getlist('frames')  # Get selected frames as a list

        # Format dates
        start_day_month = f"{start_month}-{start_day}"
        end_day_month = f"{end_month}-{end_day}" if end_month and end_day else None

        # Create a new Event
        new_event = Event(
            name=name,
            start_day_month=start_day_month,
            end_day_month=end_day_month,
            event_times=event_times,
            category_id=category_id
        )

        # Link selected frames to the event
        new_event.frames = PhotoFrame.query.filter(PhotoFrame.id.in_(selected_frame_ids)).all()
        db.session.add(new_event)
        db.session.commit()

        flash('New event added successfully!')
        return redirect(url_for('events'))

    return render_template('add_event.html', categories=categories, frames=frames)

@app.route('/edit_event/<int:id>', methods=['GET', 'POST'])
def edit_event(id):
    event = Event.query.get_or_404(id)
    categories = Category.query.all()
    frames = PhotoFrame.query.all()
    
    if request.method == 'POST':
        # Form data
        name = request.form['name']
        start_month = request.form['start_month']
        start_day = request.form['start_day']
        end_month = request.form['end_month']
        end_day = request.form['end_day']
        event_times = ','.join(request.form.getlist('event_time'))
        category_id = request.form.get('category_id')
        selected_frame_ids = request.form.getlist('frames')  # Get selected frames as a list

        # Update event properties
        event.name = name  # Update the name
        event.start_day_month = f"{start_month}-{start_day}"
        event.end_day_month = f"{end_month}-{end_day}" if end_month and end_day else None
        event.event_times = event_times
        event.category_id = category_id

        # Update linked frames
        event.frames = PhotoFrame.query.filter(PhotoFrame.id.in_(selected_frame_ids)).all()
        db.session.commit()
        
        flash('Event updated successfully!')
        return redirect(url_for('events'))

    # Pre-select frames linked to this event
    selected_frame_ids = [frame.id for frame in event.frames]
    return render_template('edit_event.html', event=event, categories=categories, frames=frames, selected_frame_ids=selected_frame_ids)

@app.route('/delete_event/<int:id>', methods=['POST'])
def delete_event(id):
    event = Event.query.get_or_404(id)
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted successfully!')
    return redirect(url_for('events'))

def index_folders():
    """Scans both shared and local folders and saves the structure to cache with orientation data."""
    folders = {}

    # Helper function to determine orientation
    def determine_orientation(image_path):
        with Image.open(image_path) as img:
            width, height = img.size
            if width > height:
                return "Horizontal"
            elif height > width:
                return "Vertical"
            else:
                return "Square"

    # Index images in the shared folder if it exists
    if os.path.exists(SHARED_IMAGES_PATH):
        for folder_name in os.listdir(SHARED_IMAGES_PATH):
            folder_path = os.path.join(SHARED_IMAGES_PATH, folder_name)
            
            if os.path.isdir(folder_path):
                images = []
                for filename in os.listdir(folder_path):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        image_path = os.path.join(folder_path, filename)
                        orientation = determine_orientation(image_path)  # Get orientation
                        images.append({
                            "name": filename,
                            "orientation": orientation
                        })
                folders[f"Shared - {folder_name}"] = images
    else:
        folders["Shared - Folder Missing"] = [{"name": "No shared images folder is mounted.", "orientation": None}]

    # Index images in the local folder if it exists
    if os.path.exists(LOCAL_IMAGES_PATH):
        for folder_name in os.listdir(LOCAL_IMAGES_PATH):
            folder_path = os.path.join(LOCAL_IMAGES_PATH, folder_name)
            
            if os.path.isdir(folder_path):
                images = []
                for filename in os.listdir(folder_path):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        image_path = os.path.join(folder_path, filename)
                        orientation = determine_orientation(image_path)  # Get orientation
                        images.append({
                            "name": filename,
                            "orientation": orientation
                        })
                folders[f"Local - {folder_name}"] = images
    else:
        folders["Local - Folder Missing"] = [{"name": "No local images folder found.", "orientation": None}]

    # Save the indexed structure to a JSON cache file
    with open(CACHE_FILE_PATH, 'w') as cache_file:
        json.dump(folders, cache_file)
    return folders

def load_cached_folders():
    """Loads the cached folder structure if it's still valid, otherwise re-indexes."""
    if os.path.exists(CACHE_FILE_PATH):
        cache_age = time.time() - os.path.getmtime(CACHE_FILE_PATH)
        if cache_age < CACHE_DURATION:
            try:
                with open(CACHE_FILE_PATH, 'r') as cache_file:
                    return json.load(cache_file)
            except (json.JSONDecodeError, IOError):
                pass

    return index_folders()

@app.route('/images')
def images():
    folders = load_cached_folders()
    return render_template('images.html', folders=folders)

@app.route('/refresh_images')
def refresh_images():
    """Route to manually refresh the image cache."""
    index_folders()  # Refresh the cache
    return redirect(url_for('images'))  # Redirect back to the images page

@app.route('/categories', methods=['GET', 'POST'])
def categories():
    # Fetch indexed folders from the images page cache
    folders = load_cached_folders().keys()  # Keys represent folder names
    
    if request.method == 'POST':
        name = request.form['name']
        linked_folders = request.form.getlist('linked_folders')  # Get selected folders as a list

        # Validate that at least one folder is selected
        if not linked_folders:
            flash("Please select at least one folder.")
            return redirect(url_for('categories'))

        # Ensure unique category names
        if Category.query.filter_by(name=name).first():
            flash("Category name already exists. Please choose a different name.")
            return redirect(url_for('categories'))

        # Join selected folders into a comma-separated string
        linked_folders_str = ','.join(linked_folders)

        # Create new category
        new_category = Category(name=name, linked_folders=linked_folders_str)
        db.session.add(new_category)
        db.session.commit()

        flash('New category added successfully!')
        return redirect(url_for('categories'))

    # Retrieve all categories for display
    categories = Category.query.all()
    return render_template('categories.html', categories=categories, folders=folders)

@app.route('/delete_category/<int:id>', methods=['POST'])
def delete_category(id):
    category = Category.query.get_or_404(id)
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted successfully!')
    return redirect(url_for('categories'))

@app.route('/external_events')
def external_events():
    external_events = ExternalEvent.query.all()
    return render_template('external_events.html', external_events=external_events)

@app.route('/add_external_event', methods=['GET', 'POST'])
def add_external_event():
    categories = Category.query.all()
    frames = PhotoFrame.query.all()
    
    if request.method == 'POST':
        name = request.form['name']  # Capture the name field
        linkname = request.form['linkname']  # Capture the name field
        event_times = ','.join(request.form.getlist('event_time'))
        category_id = request.form.get('category_id')
        selected_frame_ids = request.form.getlist('frames')

        new_external_event = ExternalEvent(
            name=name,
            linkname=linkname,
            event_times=event_times,
            category_id=category_id
        )

        new_external_event.frames = PhotoFrame.query.filter(PhotoFrame.id.in_(selected_frame_ids)).all()
        db.session.add(new_external_event)
        db.session.commit()

        flash('New external event added successfully!')
        return redirect(url_for('external_events'))

    return render_template('add_external_event.html', categories=categories, frames=frames)

@app.route('/edit_external_event/<int:id>', methods=['GET', 'POST'])
def edit_external_event(id):
    external_event = ExternalEvent.query.get_or_404(id)
    categories = Category.query.all()
    frames = PhotoFrame.query.all()
    
    if request.method == 'POST':
        name = request.form['name']
        linkname = request.form['linkname']
        event_times = ','.join(request.form.getlist('event_time'))
        category_id = request.form.get('category_id')
        selected_frame_ids = request.form.getlist('frames')

        # Update external_event attributes
        external_event.name = name  # Update the name
        external_event.event_times = event_times
        external_event.category_id = category_id
        external_event.frames = PhotoFrame.query.filter(PhotoFrame.id.in_(selected_frame_ids)).all()
        
        db.session.commit()
        flash('External event updated successfully!')
        return redirect(url_for('external_events'))

    selected_frame_ids = [frame.id for frame in external_event.frames]
    return render_template('edit_external_event.html', external_event=external_event, categories=categories, frames=frames, selected_frame_ids=selected_frame_ids)

@app.route('/delete_external_event/<int:id>', methods=['POST'])
def delete_external_event(id):
    external_event = ExternalEvent.query.get_or_404(id)
    db.session.delete(external_event)
    db.session.commit()
    flash('External event deleted successfully!')
    return redirect(url_for('external_events'))

@app.route('/random_image/<int:category_id>/', defaults={'orientation': None})
@app.route('/random_image/<int:category_id>/<string:orientation>')
def random_image(category_id, orientation):
    # Retrieve the category from the database
    category = Category.query.get_or_404(category_id)
    
    # Load cached folders and images data
    folders = load_cached_folders()

    # Define orientation mappings
    orientation_map = {
        'h': 'Horizontal',
        'v': 'Vertical',
        's': 'Square'
    }
    orientation_filter = orientation_map.get(orientation)

    # Gather image paths based on category folders and orientation
    image_paths = []
    for folder_name in category.linked_folders.split(','):
        folder_name = folder_name.strip()
        
        # Retrieve images from the cached data
        folder_images = folders.get(folder_name)
        if folder_images:
            for image_info in folder_images:
                # Include square images for both horizontal and vertical requests
                if (
                    not orientation_filter or 
                    image_info["orientation"] == orientation_filter or 
                    (orientation_filter in ['Horizontal', 'Vertical'] and image_info["orientation"] == "Square")
                ):
                    # Construct the image path
                    image_path = os.path.join(
                        SHARED_IMAGES_BASE if folder_name.startswith("Shared - ") else LOCAL_IMAGES_BASE,
                        folder_name.split(" - ", 1)[1].strip(),
                        image_info["name"]
                    )
                    image_paths.append(image_path)

    # Choose a random image path if any images were found
    if image_paths:
        chosen_image = random.choice(image_paths)
        return send_from_directory(directory=os.path.dirname(chosen_image), path=os.path.basename(chosen_image))
    else:
        return "No images available for this category and orientation.", 404

def get_script_path(screen_type_name):
    # Define the path to the pyscripts folder relative to the current file
    pyscripts_folder = os.path.join(os.path.dirname(__file__), 'pyscripts')
    
    # Retrieve the screen type entry from the database
    screen_type = ScreenType.query.filter_by(name=screen_type_name).first()
    if screen_type:
        # Join the pyscripts folder path with the script filename
        return os.path.join(pyscripts_folder, screen_type.script_filename)
    
    return None

@app.route('/externalevent=<linkname>=<action>', methods=['GET'])
def toggle_external_event(linkname, action):
    # Find the external event by its Link Name
    external_event = ExternalEvent.query.filter_by(linkname=linkname).first()
    
    if not external_event:
        return f"No external event found with Link Name '{linkname}'", 404
    
    # Check action and apply it only if necessary
    if action == 'on':
        # Activate the external event only if not already active based on category_id
        already_active = all(frame.category_id == external_event.category_id for frame in external_event.frames)
        if already_active:
            return f"External event '{linkname}' is already active.", 200
        
        for frame in external_event.frames:
            frame.category_id = external_event.category_id
            frame.active_wake_up_times = external_event.event_times  # Set wake-up times from the event
            db.session.add(frame)
            
            # Write the active wake-up times to the frame's txt file
            write_wake_up_times_to_file(frame.id_code, frame.active_wake_up_times)
        
        db.session.commit()
        return f"External event '{linkname}' activated.", 200

    elif action == 'off':
        # Deactivate the external event only if it's currently active based on category_id
        already_inactive = all(frame.category_id is None for frame in external_event.frames)
        if already_inactive:
            return f"External event '{linkname}' is already inactive.", 200
        
        for frame in external_event.frames:
            frame.category_id = None  # Reset category if needed
            frame.active_wake_up_times = frame.wake_up_times  # Reset to default wake-up times
            db.session.add(frame)
            
            # Write the reset wake-up times to the frame's txt file
            write_wake_up_times_to_file(frame.id_code, frame.active_wake_up_times)
        
        db.session.commit()
        return f"External event '{linkname}' deactivated.", 200
    
    else:
        return "Invalid action. Use 'on' or 'off'.", 400

@app.route('/runscript')
def run_script():
    output = ""
    try:
        output = check_and_run_scripts_for_upcoming_hour()
    except Exception as e:
        output += f"<br>Exception occurred: {e}"
    
    # Render output to the webpage
    return render_template_string(f"<h1>Script Output:</h1><p>{output}</p>")

def check_and_run_scripts_for_upcoming_hour():
    log_output = ""  # Collect logs here
    with app.app_context():
        try:
            upcoming_hour = (datetime.now() + timedelta(minutes=30)).hour

            frames = PhotoFrame.query.all()
            for frame in frames:
                if frame.active_wake_up_times:
                    active_hours = [int(hour.strip()) for hour in frame.active_wake_up_times.split(',')]
                    if upcoming_hour in active_hours:
                        screen_type = ScreenType.query.filter_by(name=frame.screen_type).first()
                        if not screen_type:
                            log_output += f"No screen type found for frame {frame.id_code}<br>"
                            continue

                        script_path = get_script_path(screen_type.name)
                        if not script_path:
                            log_output += f"No script path found for screen type {screen_type.name}<br>"
                            continue

                        orientation = screen_type.orientation.lower()

                        category = Category.query.get(frame.category_id)
                        if not category:
                            log_output += f"No category found for frame {frame.id_code}<br>"
                            continue

                        random_image_path = pick_random_image_from_category(category, orientation)
                        if not random_image_path:
                            log_output += f"No image found in category for frame {frame.id_code}<br>"
                            continue

                        # Define the frame output path within the loop
                        frame_output_name = os.path.join(STATIC_FOLDER_PATH, f"frame{frame.id_code}.h")

                        command = [
                            "python3", script_path,
                            orientation,
                            random_image_path,
                            frame_output_name
                        ]
                        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        stdout, stderr = process.communicate()
                        
                        # Capture stdout and stderr
                        log_output += f"Output for frame {frame.id_code}: {stdout.decode()}<br>"
                        if stderr:
                            log_output += f"Error for frame {frame.id_code}: {stderr.decode()}<br>"

        except Exception as e:
            log_output += f"Exception occurred: {e}<br>"
    
    return log_output

def schedule_task():
    """Run check_and_run_scripts_for_upcoming_hour once every hour at the :31 minute mark."""
    while True:
        now = datetime.now()
        # Calculate the next :31 minute mark
        if now.minute < 31:
            next_run = now.replace(minute=31, second=0, microsecond=0)
        else:
            next_run = (now + timedelta(hours=1)).replace(minute=31, second=0, microsecond=0)

        wait_seconds = (next_run - now).total_seconds()
        time.sleep(wait_seconds)  # Sleep until the next :31 minute mark
        
        # Run the script
        with app.app_context():
            try:
                check_and_run_scripts_for_upcoming_hour()
            except Exception as e:
                print(f"Error executing script: {e}")

# Start the background thread for scheduled execution
task_thread = threading.Thread(target=schedule_task)
task_thread.daemon = True  # Ensure the thread stops when the program exits
task_thread.start()


if __name__ == '__main__':
    app.run()