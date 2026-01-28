import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io

# --- 1. SMART FACE CROP FUNCTION (Unchanged) ---
def smart_face_crop(pil_image, target_w=300, target_h=400):
    """
    Detects a face, adds padding, crops, and resizes to target dimensions.
    """
    # Fix Orientation
    pil_image = ImageOps.exif_transpose(pil_image)

    # Convert to OpenCV format
    img_np = np.array(pil_image.convert('RGB'))
    cv_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # Load Face Detector
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)

    # Detect faces
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))

    status_text = ""
    
    if len(faces) > 0:
        status_text = "Face detected."
        largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
        x, y, w, h = largest_face

        # Add Padding
        pad_h = int(h * 0.25)
        pad_w = int(w * 0.15)

        img_h_cv, img_w_cv, _ = cv_img.shape
        y1 = max(0, y - pad_h)
        y2 = min(img_h_cv, y + h + pad_h)
        x1 = max(0, x - pad_w)
        x2 = min(img_w_cv, x + w + pad_w)

        cropped_cv = cv_img[y1:y2, x1:x2]
        img_to_resize = Image.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
    else:
        status_text = "No face detected. Center crop used."
        img_to_resize = pil_image

    # Smart Resize
    final_img = ImageOps.fit(
        img_to_resize, 
        (target_w, target_h), 
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )

    return final_img, status_text

# --- 2. VERTICAL CARD GENERATOR ---
def generate_vertical_card(name, id_number, role, photo_upload):
    # CR80 Vertical Dimensions @ 300 DPI
    # Swapped: Width is now thinner, Height is taller
    DPI = 300
    WIDTH = int(2.125 * DPI)  # approx 637 px
    HEIGHT = int(3.370 * DPI) # approx 1011 px
    
    # Colors
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    BLUE = (0, 50, 150)
    GREY_TEXT = (80, 80, 80)
    
    # Create Canvas
    card = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(card)
    
    # --- A. HEADER ---
    header_height = 120
    draw.rectangle([(0, 0), (WIDTH, header_height)], fill=BLUE)
    
    # Fonts
    try:
        # Slightly smaller fonts for vertical width constraints
        header_font = ImageFont.truetype("arial.ttf", 50)
        title_font = ImageFont.truetype("arial.ttf", 45)  # For Name
        subtitle_font = ImageFont.truetype("arial.ttf", 30) # For Labels
        role_font = ImageFont.truetype("arial.ttf", 35)     # For Role
    except IOError:
        header_font = ImageFont.load_default()
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        role_font = ImageFont.load_default()

    # Draw Header Text (Centered)
    # anchor="mm" means we position based on the Middle-Middle of the text
    draw.text((WIDTH/2, header_height/2), "EMPLOYEE ID", font=header_font, fill=WHITE, anchor="mm")

    # --- B. PHOTO (Centered) ---
    photo_w, photo_h = 300, 400
    # Calculate X to center the photo: (CardWidth - PhotoWidth) / 2
    photo_x = (WIDTH - photo_w) // 2 
    photo_y = 160 # Start a bit below the header
    
    crop_status = ""

    if photo_upload is not None:
        try:
            raw_img = Image.open(photo_upload)
            processed_img, crop_status = smart_face_crop(raw_img, photo_w, photo_h)
            
            # Border
            img_with_border = ImageOps.expand(processed_img, border=4, fill=BLACK)
            
            # Paste (Adjust x/y for border size)
            card.paste(img_with_border, (photo_x - 4, photo_y - 4))
        except Exception as e:
            st.error(f"Error: {e}")
    else:
        # Placeholder
        draw.rectangle([(photo_x, photo_y), (photo_x+photo_w, photo_y+photo_h)], outline=BLACK)
        draw.text((WIDTH/2, photo_y + 180), "No Photo", fill=BLACK, anchor="mm")

    # --- C. TEXT DETAILS (Centered Below Photo) ---
    # We use anchor="ma" (Middle-Ascender) or "mt" (Middle-Top) for easy centering
    
    # Name
    current_y = photo_y + photo_h + 50
    draw.text((WIDTH/2, current_y), name, font=title_font, fill=BLACK, anchor="mt")
    
    # Role
    current_y += 60
    draw.text((WIDTH/2, current_y), role, font=role_font, fill=BLUE, anchor="mt")
    
    # Divider Line
    line_y = current_y + 60
    draw.line([(100, line_y), (WIDTH-100, line_y)], fill=GREY_TEXT, width=2)

    # ID Number Label
    current_y = line_y + 30
    draw.text((WIDTH/2, current_y), "ID NUMBER", font=subtitle_font, fill=GREY_TEXT, anchor="mt")
    
    # ID Number Value
    current_y += 40
    draw.text((WIDTH/2, current_y), id_number, font=title_font, fill=BLACK, anchor="mt")

    # Optional: Bottom Bar
    draw.rectangle([(0, HEIGHT-30), (WIDTH, HEIGHT)], fill=BLUE)

    return card, crop_status

# --- 3. STREAMLIT INTERFACE ---
st.set_page_config(page_title="Vertical ID Gen", layout="centered")

st.title("🪪 Vertical ID Card Generator")
st.write("Generates a standard CR80 Portrait ID (2.125\" x 3.37\").")

with st.form("id_card_form"):
    col1, col2 = st.columns(2)
    with col1:
        name_in = st.text_input("Full Name", "Jane Doe")
        role_in = st.text_input("Role", "Project Manager")
    with col2:
        id_in = st.text_input("ID Number", "99887766")
        photo_in = st.file_uploader("Upload Photo", type=["jpg", "png", "jpeg"])
        
    submitted = st.form_submit_button("Generate Vertical Card")

if submitted:
    if name_in and id_in:
        final_card, status_msg = generate_vertical_card(name_in, id_in, role_in, photo_in)
        
        if "No face" in status_msg:
            st.warning(status_msg)
        
        # Display
        st.image(final_card, caption="Vertical Preview", use_container_width=True)

        # Download
        buf = io.BytesIO()
        final_card.save(buf, format="PNG")
        byte_im = buf.getvalue()

        st.download_button(
            label="Download ID Card",
            data=byte_im,
            file_name=f"{name_in}_ID_Vertical.png",
            mime="image/png"
        )
