import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io

# --- 1. SMART FACE CROP FUNCTION ---
def smart_face_crop(pil_image, target_w=300, target_h=400):
    """
    Detects a face, adds padding, crops, and resizes to target dimensions.
    Falls back to center-crop if no face is detected.
    """
    # Fix Orientation from phone cameras
    pil_image = ImageOps.exif_transpose(pil_image)

    # Convert to OpenCV format (BGR numpy array)
    img_np = np.array(pil_image.convert('RGB'))
    cv_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    
    # Convert to grayscale for detection
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # Load Face Detector
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)

    # Detect faces
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))

    status_text = ""
    
    if len(faces) > 0:
        status_text = f"Face detected. Cropping to fit."
        # Find largest face
        largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
        x, y, w, h = largest_face

        # Add Padding (25% vertical, 15% horizontal)
        pad_h = int(h * 0.25)
        pad_w = int(w * 0.15)

        img_h_cv, img_w_cv, _ = cv_img.shape
        y1 = max(0, y - pad_h)
        y2 = min(img_h_cv, y + h + pad_h)
        x1 = max(0, x - pad_w)
        x2 = min(img_w_cv, x + w + pad_w)

        # Crop
        cropped_cv = cv_img[y1:y2, x1:x2]
        
        # Convert back to PIL
        img_to_resize = Image.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
    else:
        status_text = "No face detected. Using center crop."
        img_to_resize = pil_image

    # Final Smart Resize
    final_img = ImageOps.fit(
        img_to_resize, 
        (target_w, target_h), 
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )

    return final_img, status_text

# --- 2. ID CARD GENERATOR FUNCTION ---
def generate_card(name, id_number, role, photo_upload):
    # CR80 Dimensions @ 300 DPI
    DPI = 300
    WIDTH = int(3.370 * DPI)  # 1011 px
    HEIGHT = int(2.125 * DPI) # 637 px
    
    # Colors
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    BLUE = (0, 50, 150)
    
    # Create Canvas
    card = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(card)
    
    # Draw Header
    header_height = 120
    draw.rectangle([(0, 0), (WIDTH, header_height)], fill=BLUE)
    
    # Fonts
    try:
        title_font = ImageFont.truetype("arial.ttf", 60)
        subtitle_font = ImageFont.truetype("arial.ttf", 35)
        header_font = ImageFont.truetype("arial.ttf", 65)
        role_font = ImageFont.truetype("arial.ttf", 45)
    except IOError:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        role_font = ImageFont.load_default()

    # Draw Header Text
    draw.text((30, 25), "EMPLOYEE ID", font=header_font, fill=WHITE)

    # --- PROCESS PHOTO ---
    photo_w, photo_h = 300, 400
    photo_x, photo_y = 50, 150
    crop_status = ""

    if photo_upload is not None:
        try:
            raw_img = Image.open(photo_upload)
            
            # --- USE SMART CROP HERE ---
            processed_img, crop_status = smart_face_crop(raw_img, photo_w, photo_h)
            
            # Add Border
            img_with_border = ImageOps.expand(processed_img, border=3, fill=BLACK)
            
            # Paste onto card
            card.paste(img_with_border, (photo_x, photo_y))
        except Exception as e:
            st.error(f"Error processing image: {e}")
    else:
        # Placeholder
        draw.rectangle([(photo_x, photo_y), (photo_x+photo_w, photo_y+photo_h)], outline=BLACK)
        draw.text((photo_x + 80, photo_y + 180), "No Photo", fill=BLACK)

    # --- DRAW TEXT DETAILS ---
    text_x = 400
    text_y = 180
    spacing = 110

    # Name
    draw.text((text_x, text_y), "Name:", font=subtitle_font, fill=BLUE)
    draw.text((text_x, text_y + 40), name, font=title_font, fill=BLACK)

    # Role
    draw.text((text_x, text_y + spacing), "Role:", font=subtitle_font, fill=BLUE)
    draw.text((text_x, text_y + spacing + 40), role, font=role_font, fill=BLACK)

    #
