import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageOps
import io

# --- THE SMART FACE CROP FUNCTION ---
def smart_face_crop(pil_image, target_w=300, target_h=400):
    """
    Detects a face, adds padding, crops, and resizes to target dimensions.
    Falls back to center-crop if no face is detected.
    """
    # 1. Fix Orientation from phone cameras
    pil_image = ImageOps.exif_transpose(pil_image)

    # 2. Convert PIL image (RGB) to OpenCV format (BGR numpy array)
    # Convert to numpy array
    img_np = np.array(pil_image.convert('RGB'))
    # Switch RGB to BGR for OpenCV
    cv_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    
    # Convert to grayscale for detection
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # 3. Load OpenCV Face Detector (Haar Cascade)
    # cv2.data.haarcascades points to where OpenCV installed the XML files
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)

    # Detect faces
    # scaleFactor=1.1, minNeighbors=5 are standard tuning parameters
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))

    status_text = ""
    
    if len(faces) > 0:
        status_text = f"Found {len(faces)} face(s). Cropping largest."
        # Find the largest face if multiple exist -> max area (w * h)
        # face format is (x, y, width, height)
        largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
        x, y, w, h = largest_face

        # 4. Define Padding (Crucial for ID photos)
        # We don't want a tight crop onto the chin/forehead.
        # Let's add ~25% padding to height and ~15% to width.
        pad_h = int(h * 0.25)
        pad_w = int(w * 0.15)

        # Calculate new coordinates ensuring they don't go off the image edge
        img_h_cv, img_w_cv, _ = cv_img.shape
        y1 = max(0, y - pad_h)
        y2 = min(img_h_cv, y + h + pad_h)
        x1 = max(0, x - pad_w)
        x2 = min(img_w_cv, x + w + pad_w)

        # Crop using numpy slicing [rows, columns]
        cropped_cv = cv_img[y1:y2, x1:x2]
        
        # Convert back to PIL RGB
        img_to_resize = Image.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
    else:
        status_text = "No face clearly detected. Using center crop."
        # Fallback to the original whole image
        img_to_resize = pil_image

    # 5. Final Resize using Lanczos (high quality resampling)
    # ImageOps.fit ensures the cropped area fills the target dimensions perfectly
    final_img = ImageOps.fit(
        img_to_resize, 
        (target_w, target_h), 
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )

    return final_img, status_text


# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Smart Photo Cropper", layout="wide")

st.title("📷 Smart Face Cropper for ID Cards")
st.write("Upload a photo. The app will attempt to detect the face and crop it perfectly for a 300x400 ID slot.")

uploaded_file = st.file_uploader("Choose an image...", type=['jpg', 'jpeg', 'png'])

if uploaded_file is not None:
    col1, col2 = st.columns(2)
    
    # Load original image
    original_image = Image.open(uploaded_file)
    
    with col1:
        st.subheader("Original")
        # Use expander so huge photos don't take up too much space
        with st.expander("View Original Image", expanded=True):
            st.image(original_image, use_container_width=True)

    with col2:
        st.subheader("Smart Crop Preview (300x400)")
        with st.spinner("Detecting face and cropping..."):
            # Run the smart crop function
            processed_img, status = smart_face_crop(original_image, target_w=300, target_h=400)
            
            # Display status tag
            if "Found" in status:
                st.success(status)
            else:
                st.warning(status)
                
            # Show the result
            st.image(processed_img)
            
            # Download button for the processed image
            buf = io.BytesIO()
            processed_img.save(buf, format="PNG")
            byte_im = buf.getvalue()
            st.download_button(
                label="Download Processed Photo",
                data=byte_im,
                file_name="smart_cropped_photo.png",
                mime="image/png"
            )
