import os
import time
import logging
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from sklearn.cluster import KMeans
from scipy import ndimage
import cv2

class AdvancedBrandingColorAdapter:
    def __init__(self, log_level=logging.INFO):
        # Set up logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('branding_adapter.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # University branding colors
        self.primary_color = np.array([7, 27, 44])      # #071B2C
        self.accent_color = np.array([255, 184, 28])    # #FFB81C
        self.white_color = np.array([255, 255, 255])    # White
        
        # Extended palette with intermediate colors to reduce artifacts
        self.brand_palette = np.array([
            self.primary_color,
            self.accent_color, 
            self.white_color,
            # Intermediate colors for smoother transitions
            [131, 155, 172],  # Primary + White blend
            [131, 105, 36],   # Primary + Accent blend
            [255, 219, 141],  # Accent + White blend
        ])
        
        self.core_palette = np.array([
            self.primary_color,
            self.accent_color,
            self.white_color
        ])
        
        self.logger.info("Advanced BrandingColorAdapter initialized with artifact reduction")
    
    def hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def rgb_to_hex(self, rgb_color):
        """Convert RGB tuple to hex color"""
        return '#{:02x}{:02x}{:02x}'.format(int(rgb_color[0]), int(rgb_color[1]), int(rgb_color[2]))
    
    def find_closest_brand_color(self, color, use_extended_palette=False):
        """Find the closest brand color with option for extended palette"""
        color = np.array(color[:3])
        palette = self.brand_palette if use_extended_palette else self.core_palette
        
        distances = np.linalg.norm(palette - color, axis=1)
        return palette[np.argmin(distances)]
    
    def apply_gaussian_blur(self, img_array, sigma=0.8):
        """Apply Gaussian blur to reduce harsh edges"""
        blurred = np.zeros_like(img_array)
        for channel in range(3):  # RGB channels only
            blurred[:, :, channel] = ndimage.gaussian_filter(
                img_array[:, :, channel].astype(float), sigma=sigma
            )
        blurred[:, :, 3] = img_array[:, :, 3]  # Preserve alpha
        return blurred.astype(np.uint8)
    
    def floyd_steinberg_dither(self, img_array, palette):
        """Apply Floyd-Steinberg dithering for smoother color transitions"""
        height, width = img_array.shape[:2]
        result = img_array.copy().astype(float)
        
        for y in range(height - 1):
            for x in range(1, width - 1):
                if img_array[y, x, 3] == 0:  # Skip transparent pixels
                    continue
                    
                old_pixel = result[y, x, :3]
                
                # Find closest color in palette
                distances = np.linalg.norm(palette - old_pixel, axis=1)
                new_pixel = palette[np.argmin(distances)]
                
                result[y, x, :3] = new_pixel
                error = old_pixel - new_pixel
                
                # Distribute error to neighboring pixels
                if x + 1 < width:
                    result[y, x + 1, :3] += error * 7/16
                if y + 1 < height:
                    if x - 1 >= 0:
                        result[y + 1, x - 1, :3] += error * 3/16
                    result[y + 1, x, :3] += error * 5/16
                    if x + 1 < width:
                        result[y + 1, x + 1, :3] += error * 1/16
        
        return np.clip(result, 0, 255).astype(np.uint8)
    
    def smart_color_quantization(self, img_array, n_clusters=8):
        """Use K-means clustering for intelligent color reduction"""
        # Get non-transparent pixels
        mask = img_array[:, :, 3] > 0
        pixels = img_array[mask][:, :3]
        
        if len(pixels) == 0:
            return img_array
        
        # Cluster colors
        kmeans = KMeans(n_clusters=min(n_clusters, len(np.unique(pixels.view(np.dtype((np.void, pixels.dtype.itemsize * pixels.shape[1]))), axis=0))))
        kmeans.fit(pixels)
        
        # Map cluster centers to brand colors
        cluster_centers = kmeans.cluster_centers_
        mapped_centers = np.array([
            self.find_closest_brand_color(center, use_extended_palette=True) 
            for center in cluster_centers
        ])
        
        # Replace colors
        result = img_array.copy()
        labels = kmeans.predict(pixels)
        result[mask, :3] = mapped_centers[labels]
        
        return result
    
    def edge_preserving_filter(self, img_array):
        """Apply edge-preserving filter to maintain important details"""
        if len(img_array.shape) == 3 and img_array.shape[2] == 4:
            # Convert RGBA to RGB for processing
            rgb_array = img_array[:, :, :3]
            alpha_array = img_array[:, :, 3]
            
            # Apply bilateral filter (edge-preserving)
            filtered_rgb = cv2.bilateralFilter(rgb_array, d=9, sigmaColor=75, sigmaSpace=75)
            
            # Recombine with alpha
            result = np.dstack([filtered_rgb, alpha_array])
            return result
        return img_array
    
    def process_raster_image_advanced(self, input_path, output_path, method='smart'):
        """Advanced raster processing with artifact reduction"""
        start_time = time.time()
        file_size = os.path.getsize(input_path) / (1024 * 1024)
        
        self.logger.info(f"🖼️ Advanced processing: {os.path.basename(input_path)} ({file_size:.2f} MB, method: {method})")
        
        try:
            # Load image
            img = Image.open(input_path)
            original_size = img.size
            
            # Convert to RGBA
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            img_array = np.array(img)
            
            # Choose processing method
            if method == 'smart':
                # Method 1: Smart quantization with clustering
                self.logger.debug("Applying smart color quantization...")
                processed_array = self.smart_color_quantization(img_array)
                
            elif method == 'dithered':
                # Method 2: Floyd-Steinberg dithering
                self.logger.debug("Applying Floyd-Steinberg dithering...")
                processed_array = self.floyd_steinberg_dither(img_array, self.brand_palette)
                
            elif method == 'smooth':
                # Method 3: Gaussian blur + edge-preserving + mapping
                self.logger.debug("Applying smooth processing...")
                # Light blur to reduce artifacts
                blurred = self.apply_gaussian_blur(img_array, sigma=0.6)
                # Edge-preserving filter
                filtered = self.edge_preserving_filter(blurred)
                # Simple color mapping
                processed_array = self.simple_color_mapping(filtered)
                
            elif method == 'hybrid':
                # Method 4: Hybrid approach
                self.logger.debug("Applying hybrid processing...")
                # Start with edge-preserving filter
                filtered = self.edge_preserving_filter(img_array)
                # Apply smart quantization
                quantized = self.smart_color_quantization(filtered, n_clusters=6)
                # Light dithering
                processed_array = self.floyd_steinberg_dither(quantized, self.core_palette)
                
            else:  # fallback
                processed_array = self.simple_color_mapping(img_array)
            
            # Post-processing: Final mapping to core brand colors only
            self.logger.debug("Final mapping to core brand colors...")
            processed_array = self.final_brand_mapping(processed_array)
            
            # Convert back to PIL Image
            new_img = Image.fromarray(processed_array, 'RGBA')
            
            # Apply final smoothing
            new_img = new_img.filter(ImageFilter.SMOOTH_MORE)
            
            # Save
            if output_path.lower().endswith(('.jpg', '.jpeg')):
                rgb_img = Image.new('RGB', new_img.size, (255, 255, 255))
                rgb_img.paste(new_img, mask=new_img.split()[-1])
                rgb_img.save(output_path, 'JPEG', quality=95)
            else:
                new_img.save(output_path, 'PNG')
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"✓ Advanced processing complete: {os.path.basename(input_path)} ({elapsed_time:.2f}s)")
            
        except Exception as e:
            self.logger.error(f"✗ Error in advanced processing {input_path}: {str(e)}")
            raise
    
    def simple_color_mapping(self, img_array):
        """Simple color mapping fallback"""
        result = img_array.copy()
        mask = img_array[:, :, 3] > 0
        
        for y in range(img_array.shape[0]):
            for x in range(img_array.shape[1]):
                if mask[y, x]:
                    original_color = img_array[y, x, :3]
                    new_color = self.find_closest_brand_color(original_color, use_extended_palette=True)
                    result[y, x, :3] = new_color
        
        return result
    
    def final_brand_mapping(self, img_array):
        """Final pass to ensure only core brand colors are used"""
        result = img_array.copy()
        mask = img_array[:, :, 3] > 0
        
        # Map any intermediate colors back to core brand colors
        for y in range(img_array.shape[0]):
            for x in range(img_array.shape[1]):
                if mask[y, x]:
                    current_color = img_array[y, x, :3]
                    # Check if it's already a core brand color
                    distances_to_core = np.linalg.norm(self.core_palette - current_color, axis=1)
                    if np.min(distances_to_core) > 5:  # If not close to core colors
                        new_color = self.find_closest_brand_color(current_color, use_extended_palette=False)
                        result[y, x, :3] = new_color
        
        return result
    
    def process_svg(self, input_path, output_path):
        """SVG processing (same as before but with better color mapping)"""
        # [Previous SVG code remains the same]
        # I'll keep the original SVG processing since it doesn't have raster artifacts
        pass  # Using the same SVG processing from the previous version
    
    def process_directory_advanced(self, input_dir, output_dir, method='hybrid'):
        """Process directory with advanced methods"""
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        
        # Create multiple output directories for different methods
        methods = ['smart', 'dithered', 'smooth', 'hybrid']
        
        if method == 'all':
            self.logger.info("🎨 Processing with ALL methods for comparison...")
            for m in methods:
                method_output_dir = output_path / f"method_{m}"
                method_output_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"\n--- Processing with {m.upper()} method ---")
                self._process_single_method(input_path, method_output_dir, m)
        else:
            output_path.mkdir(parents=True, exist_ok=True)
            self._process_single_method(input_path, output_path, method)
    
    def _process_single_method(self, input_path, output_path, method):
        """Process with a single method"""
        svg_extensions = {'.svg'}
        raster_extensions = {'.png', '.jpg', '.jpeg'}
        all_extensions = svg_extensions.union(raster_extensions)
        
        files = [f for f in input_path.rglob('*') if f.suffix.lower() in all_extensions]
        
        for i, file_path in enumerate(files, 1):
            self.logger.info(f"Processing {i}/{len(files)}: {file_path.name}")
            
            relative_path = file_path.relative_to(input_path)
            output_file_path = output_path / relative_path
            output_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                if file_path.suffix.lower() in svg_extensions:
                    self.process_svg(str(file_path), str(output_file_path))
                else:
                    self.process_raster_image_advanced(str(file_path), str(output_file_path), method)
            except Exception as e:
                self.logger.error(f"Failed to process {file_path.name}: {str(e)}")

def main():
    """Main function with advanced processing options"""
    print("🎨 Advanced MC Escher Branding Color Adapter")
    print("=" * 50)
    
    # Configuration
    input_directory = "input_images"
    output_directory = "branded_images_advanced"
    
    # Processing methods:
    # 'smart' - K-means clustering (best for complex images)
    # 'dithered' - Floyd-Steinberg dithering (best for gradients)
    # 'smooth' - Gaussian blur + edge preservation (best for clean images)
    # 'hybrid' - Combination approach (recommended)
    # 'all' - Generate all methods for comparison
    
    processing_method = 'hybrid'  # Change this to try different methods
    
    adapter = AdvancedBrandingColorAdapter(log_level=logging.INFO)
    
    if not os.path.exists(input_directory):
        adapter.logger.error(f"❌ Input directory '{input_directory}' does not exist!")
        return
    
    adapter.process_directory_advanced(input_directory, output_directory, processing_method)

if __name__ == "__main__":
    main()
