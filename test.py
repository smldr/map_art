import requests
import json
import random
import math
import os
from xml.etree.ElementTree import Element, SubElement, tostring, parse
from xml.dom import minidom

class MapArtGenerator:
    def __init__(self):
        self.colors = {
            'background': '#071B2C',
            'roads': '#FFB81C', 
            'contours': '#FFFFFF',
            'border': '#0A2440'  # Slightly lighter than background for subtle border
        }
        
        # Port Elizabeth suburbs - only the ones you specified
        self.locations = {
            'summerstrand': (-33.9722, 25.4731),
            'richmond_hill': (-33.9543, 25.5901),
            'seaview': (-34.0089, 25.3567),
            'newton_park': (-33.9645, 25.5234),
            'mill_park': (-33.9789, 25.5123),
            'missionvale': (-33.8567, 25.5789),
            'govan_mbeki': (-33.9234, 25.5456),
            'walmer': (-33.9456, 25.5678)
        }

    def load_compass_svg(self, compass_file_path="cpm-lab-nmu.svg"):
        """Load the compass SVG file"""
        try:
            if os.path.exists(compass_file_path):
                tree = parse(compass_file_path)
                return tree.getroot()
            else:
                print(f"  Warning: Compass file '{compass_file_path}' not found")
                return None
        except Exception as e:
            print(f"  Warning: Could not load compass SVG: {e}")
            return None

    def add_compass_to_content(self, svg, compass_svg, border_width, total_width, total_height):
        """Add scaled compass INSIDE the content area, top-right corner"""
        if compass_svg is None:
            return
            
        # Calculate compass size - fit nicely with margin
        compass_size = int(border_width * 0.8)  # 80% of border width
        margin = 10  # Margin from edge of content area
        
        # Position INSIDE the content area, top-right corner
        compass_x = total_width - border_width - compass_size - margin
        compass_y = border_width + margin
        
        print(f"  Adding compass: {compass_size}×{compass_size}px at ({compass_x}, {compass_y}) [INSIDE content area, top-right]")
        
        # Create a group for the compass with transform
        compass_group = SubElement(svg, 'g')
        compass_group.set('transform', f'translate({compass_x}, {compass_y}) scale({compass_size/1440})')
        
        # Copy all elements from compass SVG into the group
        for child in compass_svg:
            compass_group.append(child)

    def calculate_bounds_from_scale(self, center_lat, center_lon, width_px, height_px, meters_per_pixel=8):
        """Calculate geographic bounds based on image dimensions and scale"""
        
        # Calculate the real-world dimensions
        width_meters = width_px * meters_per_pixel
        height_meters = height_px * meters_per_pixel
        
        # Convert meters to degrees
        lat_degrees_per_meter = 1.0 / 111000.0
        lon_degrees_per_meter = 1.0 / (111000.0 * math.cos(math.radians(center_lat)))
        
        # Calculate half-widths in degrees
        half_height_deg = (height_meters / 2) * lat_degrees_per_meter
        half_width_deg = (width_meters / 2) * lon_degrees_per_meter
        
        bounds = {
            'min_lat': center_lat - half_height_deg,
            'max_lat': center_lat + half_height_deg,
            'min_lon': center_lon - half_width_deg,
            'max_lon': center_lon + half_width_deg
        }
        
        return bounds

    def fetch_map_data(self, center_lat, center_lon, width_px, height_px, meters_per_pixel=8):
        """Fetch road and contour data using calculated bounds"""
        overpass_url = "http://overpass-api.de/api/interpreter"
        
        # Calculate exact bounds based on image dimensions and scale
        bounds = self.calculate_bounds_from_scale(center_lat, center_lon, width_px, height_px, meters_per_pixel)
        
        print(f"  Coverage: {width_px * meters_per_pixel}m × {height_px * meters_per_pixel}m at {meters_per_pixel}m/px")
        
        # Query for roads
        road_query = f"""
        [out:json][timeout:30];
        (
          way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|residential|unclassified|service|living_street)$"]
             ({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
        );
        out geom;
        """
        
        # Enhanced query for contours and natural features
        contour_query = f"""
        [out:json][timeout:30];
        (
          way["natural"="coastline"]({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
          way["waterway"~"^(river|stream|canal|drain|ditch)$"]({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
          way["natural"="water"]({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
          way["landuse"="reservoir"]({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
          way["barrier"="retaining_wall"]({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
          way["man_made"="embankment"]({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
          way["natural"="cliff"]({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
        );
        out geom;
        """
        
        roads_data = self._query_overpass(overpass_url, road_query)
        contours_data = self._query_overpass(overpass_url, contour_query)
        
        return roads_data, contours_data, bounds

    def _query_overpass(self, url, query):
        """Execute Overpass API query with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"  Fetching data (attempt {attempt + 1}/{max_retries})...")
                response = requests.post(url, data=query, timeout=45)
                if response.status_code == 200:
                    data = response.json()
                    if 'elements' in data:
                        return data
                print(f"  Attempt {attempt + 1} failed, retrying...")
            except Exception as e:
                print(f"  Attempt {attempt + 1} error: {e}")
            
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
        
        print("  All attempts failed, using fallback")
        return {'elements': []}

    def generate_synthetic_contours(self, bounds):
        """Generate synthetic contour lines within the exact bounds - optimized for tall/narrow format"""
        contours = []
        
        min_lat = bounds['min_lat']
        max_lat = bounds['max_lat']
        min_lon = bounds['min_lon']
        max_lon = bounds['max_lon']
        
        lat_center = (min_lat + max_lat) / 2
        lon_center = (min_lon + max_lon) / 2
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon
        
        # Generate contour rings optimized for tall format
        for i in range(5, 10):  # Fewer rings for narrow format
            radius_factor = 0.1 + i * 0.08
            
            points = []
            for angle in range(0, 360, 10):  # Slightly fewer points
                rad = math.radians(angle)
                
                # Adjust for tall/narrow format - compress horizontally, extend vertically
                offset_lat = lat_range * radius_factor * 0.8 * math.cos(rad)  # More vertical spread
                offset_lon = lon_range * radius_factor * 1.2 * math.sin(rad)  # Less horizontal spread
                
                # Add organic variation optimized for door shape
                variation_lat = lat_range * 0.02 * math.sin(rad * 2.5 + i * 0.7)
                variation_lon = lon_range * 0.01 * math.cos(rad * 3.2 + i * 0.5)  # Less horizontal variation
                
                contour_lat = lat_center + offset_lat + variation_lat
                contour_lon = lon_center + offset_lon + variation_lon
                
                # Clamp to bounds
                margin_lat = lat_range * 0.02
                margin_lon = lon_range * 0.05  # Bigger horizontal margin for narrow format
                contour_lat = max(min_lat + margin_lat, min(max_lat - margin_lat, contour_lat))
                contour_lon = max(min_lon + margin_lon, min(max_lon - margin_lon, contour_lon))
                
                points.append((contour_lat, contour_lon))
            
            # Close the contour
            if points:
                points.append(points[0])
                
            contours.append({
                'points': points,
                'level': i,
                'opacity': 0.15 + (i * 0.06)
            })
        
        # Add vertical ridges that work well with door format
        for ridge_id in range(3):
            ridge_points = []
            
            # Create more vertical-oriented ridges
            x_position = 0.2 + ridge_id * 0.3  # 20%, 50%, 80% across width
            base_lon = min_lon + lon_range * x_position
            
            for t in [i/15.0 for i in range(16)]:  # More points along height
                ridge_lat = min_lat + lat_range * (0.1 + t * 0.8)  # Almost full height
                
                # Add gentle horizontal wave
                wave_offset = lon_range * 0.02 * math.sin(t * math.pi * 2.5 + ridge_id)
                ridge_lon = base_lon + wave_offset
                
                # Keep within bounds
                ridge_lat = max(min_lat, min(max_lat, ridge_lat))
                ridge_lon = max(min_lon, min(max_lon, ridge_lon))
                
                ridge_points.append((ridge_lat, ridge_lon))
            
            contours.append({
                'points': ridge_points,
                'level': f'vertical_ridge_{ridge_id}',
                'opacity': 0.25
            })
        
        # Add some horizontal features for balance
        for horizontal_id in range(2):
            horizontal_points = []
            
            y_position = 0.3 + horizontal_id * 0.4  # 30% and 70% up the height
            base_lat = min_lat + lat_range * y_position
            
            for t in [i/10.0 for i in range(11)]:  # Across the width
                horizontal_lon = min_lon + lon_range * (0.1 + t * 0.8)
                
                # Add gentle vertical wave
                wave_offset = lat_range * 0.015 * math.sin(t * math.pi * 3 + horizontal_id)
                horizontal_lat = base_lat + wave_offset
                
                horizontal_points.append((horizontal_lat, horizontal_lon))
            
            contours.append({
                'points': horizontal_points,
                'level': f'horizontal_ridge_{horizontal_id}',
                'opacity': 0.2
            })
        
        return contours

    def add_border_design(self, svg, total_width, total_height, border_width, compass_svg):
        """Add subtle design elements to the border area and compass to content area"""
        if border_width < 20:
            return
        
        # Add compass INSIDE the content area, top-right
        self.add_compass_to_content(svg, compass_svg, border_width, total_width, total_height)
            
        # Add corner registration marks in border area
        mark_size = min(border_width // 3, 10)
        mark_offset = border_width // 4
        
        # All corner registration marks
        corners = [
            (mark_offset, mark_offset),  # Top-left
            (total_width - mark_offset, mark_offset),  # Top-right
            (mark_offset, total_height - mark_offset),  # Bottom-left
            (total_width - mark_offset, total_height - mark_offset)  # Bottom-right
        ]
        
        for x_pos, y_pos in corners:
            # Vertical mark
            line1 = SubElement(svg, 'line')
            line1.set('x1', str(x_pos))
            line1.set('y1', str(y_pos - mark_size))
            line1.set('x2', str(x_pos))
            line1.set('y2', str(y_pos + mark_size))
            line1.set('stroke', self.colors['roads'])
            line1.set('stroke-width', '1')
            line1.set('opacity', '0.4')
            
            # Horizontal mark
            line2 = SubElement(svg, 'line')
            line2.set('x1', str(x_pos - mark_size))
            line2.set('y1', str(y_pos))
            line2.set('x2', str(x_pos + mark_size))
            line2.set('y2', str(y_pos))
            line2.set('stroke', self.colors['roads'])
            line2.set('stroke-width', '1')
            line2.set('opacity', '0.4')

    def add_subtle_grid(self, svg, width, height, border_width, opacity=0.06):
        """Add grid optimized for door format"""
        content_x = border_width
        content_y = border_width
        content_width = width - 2 * border_width
        content_height = height - 2 * border_width
        
        # Adjust grid for door aspect ratio
        grid_size_x = random.randint(60, 100)  # Smaller horizontal spacing
        grid_size_y = random.randint(120, 180)  # Larger vertical spacing
        
        # Vertical lines (fewer, since it's narrow)
        for x in range(grid_size_x, content_width, grid_size_x):
            line = SubElement(svg, 'line')
            line.set('x1', str(content_x + x))
            line.set('y1', str(content_y))
            line.set('x2', str(content_x + x))
            line.set('y2', str(content_y + content_height))
            line.set('stroke', '#FFFFFF')
            line.set('stroke-width', '0.3')
            line.set('opacity', str(opacity))
        
        # Horizontal lines
        for y in range(grid_size_y, content_height, grid_size_y):
            line = SubElement(svg, 'line')
            line.set('x1', str(content_x))
            line.set('y1', str(content_y + y))
            line.set('x2', str(content_x + content_width))
            line.set('y2', str(content_y + y))
            line.set('stroke', '#FFFFFF')
            line.set('stroke-width', '0.3')
            line.set('opacity', str(opacity))

    def add_corner_details(self, svg, width, height, border_width):
        """Add corner details optimized for door format"""
        content_x = border_width
        content_y = border_width
        content_width = width - 2 * border_width
        content_height = height - 2 * border_width
        
        corner_size = random.randint(20, 35)
        
        # Top-left corner (compass is in top-right content area, so this is fine)
        polyline = SubElement(svg, 'polyline')
        polyline.set('points', f"{content_x},{content_y + corner_size} {content_x},{content_y} {content_x + corner_size},{content_y}")
        polyline.set('stroke', self.colors['roads'])
        polyline.set('stroke-width', '2')
        polyline.set('fill', 'none')
        polyline.set('opacity', '0.7')

        # Bottom corners
        for side in [0, 1]:
            x_pos = content_x if side == 0 else content_x + content_width
            corner_x = corner_size if side == 0 else -corner_size
            
            polyline = SubElement(svg, 'polyline')
            polyline.set('points', f"{x_pos},{content_y + content_height - corner_size} {x_pos},{content_y + content_height} {x_pos + corner_x},{content_y + content_height}")
            polyline.set('stroke', self.colors['roads'])
            polyline.set('stroke-width', '2')
            polyline.set('fill', 'none')
            polyline.set('opacity', '0.7')

    def create_svg_panel(self, location_name, compass_svg, width=600, height=1350, border_width=50, variation=0, meters_per_pixel=8):
        """Generate door-shaped SVG panel with compass inside content area"""
        if location_name not in self.locations:
            print(f"  Warning: Location {location_name} not found")
            return None
            
        center_lat, center_lon = self.locations[location_name]
        
        # Calculate total dimensions including border
        total_width = width + (2 * border_width)
        total_height = height + (2 * border_width)
        
        # Content area is the original width/height
        content_width = width
        content_height = height
        
        aspect_ratio = width / height
        print(f"  Door panel: {total_width}×{total_height}px (aspect: {aspect_ratio:.2f})")
        print(f"  Content: {content_width}×{content_height}px, border: {border_width}px")
        
        # Add variation to center point
        random.seed(hash(location_name + str(variation)))
        offset_meters = 150  # Smaller offset for narrower view
        lat_offset = (offset_meters * random.uniform(-1, 1)) / 111000.0
        lon_offset = (offset_meters * random.uniform(-1, 1)) / (111000.0 * math.cos(math.radians(center_lat)))
        
        center_lat += lat_offset
        center_lon += lon_offset
        
        # Fetch data using content dimensions
        roads_data, contours_data, bounds = self.fetch_map_data(center_lat, center_lon, content_width, content_height, meters_per_pixel)
        
        # Create SVG with total dimensions
        svg = Element('svg')
        svg.set('width', str(total_width))
        svg.set('height', str(total_height))
        svg.set('xmlns', 'http://www.w3.org/2000/svg')
        svg.set('viewBox', f'0 0 {total_width} {total_height}')
        
        # Full background (including border)
        bg = SubElement(svg, 'rect')
        bg.set('width', str(total_width))
        bg.set('height', str(total_height))
        bg.set('fill', self.colors['border'])
        
        # Content area background
        content_bg = SubElement(svg, 'rect')
        content_bg.set('x', str(border_width))
        content_bg.set('y', str(border_width))
        content_bg.set('width', str(content_width))
        content_bg.set('height', str(content_height))
        content_bg.set('fill', self.colors['background'])
        
        # Create coordinate conversion for content area (north = up)
        min_lat = bounds['min_lat']
        max_lat = bounds['max_lat']
        min_lon = bounds['min_lon']
        max_lon = bounds['max_lon']
        
        def coord_to_svg(lat, lon):
            # North (higher latitude) maps to top of door (lower y)
            x = border_width + ((lon - min_lon) / (max_lon - min_lon)) * content_width
            y = border_width + content_height - ((lat - min_lat) / (max_lat - min_lat)) * content_height
            return x, y
        
        contour_count = 0
        road_count = 0
        
        # Draw real contours first
        for element in contours_data.get('elements', []):
            if 'geometry' in element and len(element['geometry']) > 1:
                points = []
                for coord in element['geometry']:
                    x, y = coord_to_svg(coord['lat'], coord['lon'])
                    points.append(f"{x:.1f},{y:.1f}")
                
                if len(points) > 1:
                    polyline = SubElement(svg, 'polyline')
                    polyline.set('points', ' '.join(points))
                    polyline.set('stroke', self.colors['contours'])
                    polyline.set('stroke-width', str(random.uniform(0.8, 1.5)))
                    polyline.set('fill', 'none')
                    polyline.set('opacity', '0.8')
                    polyline.set('stroke-linecap', 'round')
                    contour_count += 1
        
        # Generate synthetic contours optimized for door format
        synthetic_contours = self.generate_synthetic_contours(bounds)
        
        for contour in synthetic_contours:
            if len(contour['points']) > 1:
                svg_points = []
                for lat, lon in contour['points']:
                    x, y = coord_to_svg(lat, lon)
                    svg_points.append(f"{x:.1f},{y:.1f}")
                
                polyline = SubElement(svg, 'polyline')
                polyline.set('points', ' '.join(svg_points))
                polyline.set('stroke', self.colors['contours'])
                polyline.set('stroke-width', str(random.uniform(0.5, 1.0)))
                polyline.set('fill', 'none')
                polyline.set('opacity', str(contour['opacity']))
                polyline.set('stroke-linecap', 'round')
                contour_count += 1
        
        # Draw roads
        for element in roads_data.get('elements', []):
            if 'geometry' in element and len(element['geometry']) > 1:
                highway_type = element.get('tags', {}).get('highway', '')
                
                # Road widths adjusted for door format
                width_map = {
                    'motorway': 4,
                    'motorway_link': 3,
                    'trunk': 3.5,
                    'trunk_link': 2.5,
                    'primary': 3,
                    'primary_link': 2,
                    'secondary': 2.5,
                    'secondary_link': 1.8,
                    'tertiary': 2,
                    'tertiary_link': 1.5,
                    'residential': 1.5,
                    'unclassified': 1.2,
                    'service': 0.8,
                    'living_street': 1.2
                }
                stroke_width = width_map.get(highway_type, 1.0)
                
                points = []
                for coord in element['geometry']:
                    x, y = coord_to_svg(coord['lat'], coord['lon'])
                    points.append(f"{x:.1f},{y:.1f}")
                
                if len(points) > 1:
                    polyline = SubElement(svg, 'polyline')
                    polyline.set('points', ' '.join(points))
                    polyline.set('stroke', self.colors['roads'])
                    polyline.set('stroke-width', str(stroke_width))
                    polyline.set('fill', 'none')
                    polyline.set('stroke-linecap', 'round')
                    polyline.set('stroke-linejoin', 'round')
                    road_count += 1
        
        print(f"  Added {road_count} roads and {contour_count} contours")
        
        # Add border design elements with compass INSIDE content area
        self.add_border_design(svg, total_width, total_height, border_width, compass_svg)
        
        # Add decorative overlays optimized for door format
        if variation % 3 == 0:
            self.add_subtle_grid(svg, total_width, total_height, border_width)
        
        if variation % 4 == 0:
            self.add_corner_details(svg, total_width, total_height, border_width)
        
        return svg

    def generate_panels(self, count=8, width=600, height=1350, border_width=50, meters_per_pixel=8):
        """Generate door-shaped panels with compass inside content area"""
        panels = []
        locations = list(self.locations.keys())
        
        # Load compass SVG once
        print("Loading compass SVG...")
        compass_svg = self.load_compass_svg("cpm-lab-nmu.svg")
        if compass_svg is not None:
            print("✓ Compass SVG loaded successfully")
        else:
            print("⚠ Compass SVG not found - panels will be generated without compass")
        
        total_width = width + (2 * border_width)
        total_height = height + (2 * border_width)
        aspect_ratio = width / height
        
        print(f"\nGenerating {count} door-shaped panels with compass INSIDE content area...")
        print(f"🚪 Door format: {total_width}×{total_height}px (aspect ratio: {aspect_ratio:.2f})")
        print(f"📐 Content area: {width}×{height}px")
        print(f"🛡️  Border width: {border_width}px")
        print(f"🧭 Compass: INSIDE content area, top-right corner ({border_width*0.8:.0f}×{border_width*0.8:.0f}px)")
        print(f"📍 Coverage per panel: {width*meters_per_pixel}m × {height*meters_per_pixel}m")
        print(f"🏘️  Locations: {', '.join([loc.replace('_', ' ').title() for loc in locations])}")
        print("-" * 60)
        
        for i in range(count):
            location = locations[i % len(locations)]
            variation = i // len(locations)
            
            print(f"Panel {i+1}/{count}: {location.replace('_', ' ').title()} (variation {variation})")
            
            svg = self.create_svg_panel(location, compass_svg, width, height, border_width, variation, meters_per_pixel)
            if svg is not None:
                panels.append({
                    'location': location,
                    'variation': variation,
                    'svg': svg
                })
                print("  ✓ Door panel with compass generated successfully")
            else:
                print("  ✗ Failed to generate panel")
            print()
        
        return panels

    def save_panels(self, panels, output_dir="door_panels_with_compass"):
        """Save door-shaped SVG panels with compass to files"""
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"Saving door panels with compass to '{output_dir}' directory...")
        print("-" * 60)
        
        for i, panel in enumerate(panels):
            filename = f"door_panel_compass_{i+1:02d}_{panel['location']}_v{panel['variation']}.svg"
            filepath = os.path.join(output_dir, filename)
            
            rough_string = tostring(panel['svg'], 'unicode')
            reparsed = minidom.parseString(rough_string)
            pretty = reparsed.toprettyxml(indent="  ")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(pretty)
            
            print(f"✓ Saved: {filename}")
        
        print(f"\n🎉 All {len(panels)} door panels with compass saved successfully!")
        print(f"📁 Location: {os.path.abspath(output_dir)}")

def main():
    """Main function"""
    print("=" * 70)
    print("🚗 SELF-DRIVING CAR LAB - DOOR PANELS WITH COMPASS")
    print("=" * 70)
    print("🚪 Door-shaped panels with compass INSIDE the content area")
    print(f"Colors: Roads(#FFB81C) | Background(#071B2C) | Contours(#FFFFFF) | Border(#0A2440)")
    print()
    
    generator = MapArtGenerator()
    
    try:
        # Generate door-shaped panels with compass inside content area
        panels = generator.generate_panels(
            count=8, 
            width=600,            # Door width (narrow)
            height=1350,          # Door height (tall) - 36:80 ratio ≈ 0.44
            border_width=50,      # Safety border 
            meters_per_pixel=8    # Same detail level
        )
        
        if panels:
            generator.save_panels(panels)
            print(f"\n📋 SUMMARY:")
            print(f"   🚪 Door panels generated: {len(panels)}")
            print(f"   📐 Size: 700×1450px (600×1350px + 50px borders)")
            print(f"   🧭 Compass INSIDE content area, top-right corner")
            print(f"   📏 Door aspect ratio: 0.44 (width:height)")
            print(f"   🎯 Perfect for lab door vinyl application!")
            print(f"   ✅ Ready for vinyl printing with compass branding!")
        else:
            print("❌ No panels generated")
            
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
