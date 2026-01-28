import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io

# --- 1. The ID Card Generation Function ---
def generate_card(name, id_number, photo_upload):
    # CR80 Dimensions at 300 DPI
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
    
    # Load Fonts
    # We use load_default to ensure it works on any server (Streamlit Cloud, Linux, etc.)
    # For custom fonts, you would put the .ttf file in the folder and load it.
    try:
        title_font = ImageFont.truetype("arial.ttf", 60)
        subtitle_font = ImageFont.truetype("arial.ttf", 35)
        header_font = ImageFont.truetype("arial.ttf", 60)
    except IOError:
        # Fallback for servers that don't have Arial
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        header_font = ImageFont.load_default()

    # Draw Header Text
    draw.text((30, 30), "EMPLOYEE ID", font=header_font, fill=WHITE)

    # --- Process Photo ---
    photo_w, photo_h = 300, 400
    photo_x, photo_y = 50, 150
    
    if photo_upload is not None:
        try:
            # Open the uploaded image
            img = Image.open(photo_upload)
            
            # Auto-orient (fixes rotation issues from phone cameras)
            img = ImageOps.exif_transpose(img)
            
            # Resize/Crop
            img = ImageOps.fit(img, (photo_w, photo_h), centering=(0.5, 0.5))
            
            # Border
            img = ImageOps.expand(img, border=3, fill=BLACK)
            
            # Paste
            card.paste(img, (photo_x, photo_y))
        except Exception as e:
            st.error(f"Error processing image: {e}")
    else:
        # Placeholder box if no image uploaded
        draw.rectangle([(photo_x, photo_y), (photo_x+photo_w, photo_y+photo_h)], outline=BLACK)
        draw.text((photo_x + 80, photo_y + 180), "No Photo", fill=BLACK)

    # --- Draw Text ---
    text_x = 400
    text_y = 200

    draw.text((text_x, text_y), "Name:", font=subtitle_font, fill=BLUE)
    draw.text((text_x, text_y + 45), name, font=title_font, fill=BLACK)

    draw.text((text_x, text_y + 140), "ID Number:", font=subtitle_font, fill=BLUE)
    draw.text((text_x, text_y + 185), id_number, font=title_font, fill=BLACK)

    return card

# --- 2. Streamlit Interface ---
st.title("🪪 ID Card Generator")
st.write("Upload a photo and enter details to generate a printable CR80 ID card.")

# Input Layout
col1, col2 = st.columns(2)

with col1:
    input_name = st.text_input("Full Name", "John Doe")
    input_id = st.text_input("ID Number", "12345678")

with col2:
    uploaded_file = st.file_uploader("Upload Photo", type=["jpg", "png", "jpeg"])

if st.button("Generate ID Card"):
    if input_name and input_id:
        # Generate the card
        final_card = generate_card(input_name, input_id, uploaded_file)
        
        # Display the result
        st.success("Card Generated Successfully!")
        st.image(final_card, caption="Preview", use_container_width=True)
        
        # Prepare for Download
        # We save the image into a memory buffer (BytesIO) instead of a file on disk
        buf = io.BytesIO()
        final_card.save(buf, format="PNG")
        byte_im = buf.getvalue()

        # Download Button
        st.download_button(
            label="Download ID Card (PNG)",
            data=byte_im,
            file_name=f"{input_name}_id.png",
            mime="image/png"
        )
    else:
        st.warning("Please enter both Name and ID Number.")
