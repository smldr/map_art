import requests
import json
import random
import math
import os
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

class MapArtGenerator:
    def __init__(self):
        self.colors = {
            'background': '#071B2C',
            'roads': '#FFB81C', 
            'contours': '#FFFFFF'
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

    def calculate_bounds_from_scale(self, center_lat, center_lon, width_px, height_px, meters_per_pixel=20):
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

    def fetch_map_data(self, center_lat, center_lon, width_px, height_px, meters_per_pixel=20):
        """Fetch road and contour data using calculated bounds"""
        overpass_url = "http://overpass-api.de/api/interpreter"
        
        # Calculate exact bounds based on image dimensions and scale
        bounds = self.calculate_bounds_from_scale(center_lat, center_lon, width_px, height_px, meters_per_pixel)
        
        print(f"  Scale: {meters_per_pixel}m per pixel")
        print(f"  Coverage: {width_px * meters_per_pixel}m × {height_px * meters_per_pixel}m")
        print(f"  Bounds: {bounds['min_lat']:.6f},{bounds['min_lon']:.6f} to {bounds['max_lat']:.6f},{bounds['max_lon']:.6f}")
        
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
        """Generate synthetic contour lines within the exact bounds - SIMPLIFIED VERSION"""
        contours = []
        
        min_lat = bounds['min_lat']
        max_lat = bounds['max_lat']
        min_lon = bounds['min_lon']
        max_lon = bounds['max_lon']
        
        lat_center = (min_lat + max_lat) / 2
        lon_center = (min_lon + max_lon) / 2
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon
        
        print(f"  Creating synthetic contours in bounds:")
        print(f"    Center: {lat_center:.6f}, {lon_center:.6f}")
        print(f"    Range: lat={lat_range:.6f}, lon={lon_range:.6f}")
        
        # Create simple horizontal contour lines (like elevation contours)
        for i in range(5):
            y_position = 0.2 + i * 0.15  # Evenly spaced from 20% to 80% of height
            contour_lat = min_lat + lat_range * y_position
            
            # Create a wavy line across the width
            points = []
            for x_step in range(21):  # 21 points across width
                x_position = x_step / 20.0  # 0 to 1
                contour_lon = min_lon + lon_range * x_position
                
                # Add small wave variation
                wave_offset = lat_range * 0.02 * math.sin(x_position * math.pi * 4 + i)
                final_lat = contour_lat + wave_offset
                
                points.append((final_lat, contour_lon))
            
            contours.append({
                'points': points,
                'level': i,
                'opacity': 0.3 + (i * 0.1)
            })
            
            print(f"    Contour {i}: lat {contour_lat:.6f}, {len(points)} points")
        
        # Add some vertical contours too
        for i in range(3):
            x_position = 0.25 + i * 0.25  # At 25%, 50%, 75% of width
            contour_lon = min_lon + lon_range * x_position
            
            points = []
            for y_step in range(16):  # 16 points down height
                y_position = y_step / 15.0  # 0 to 1
                contour_lat = min_lat + lat_range * y_position
                
                # Add small wave variation
                wave_offset = lon_range * 0.01 * math.sin(y_position * math.pi * 3 + i)
                final_lon = contour_lon + wave_offset
                
                points.append((contour_lat, final_lon))
            
            contours.append({
                'points': points,
                'level': f'vertical_{i}',
                'opacity': 0.25
            })
            
            print(f"    Vertical contour {i}: lon {contour_lon:.6f}, {len(points)} points")
        
        return contours

    def add_subtle_grid(self, svg, width, height, opacity=0.06):
        """Add a subtle grid pattern"""
        grid_size = random.randint(100, 160)
        
        for x in range(grid_size, width, grid_size):
            line = SubElement(svg, 'line')
            line.set('x1', str(x))
            line.set('y1', '0')
            line.set('x2', str(x))
            line.set('y2', str(height))
            line.set('stroke', '#FFFFFF')
            line.set('stroke-width', '0.3')
            line.set('opacity', str(opacity))
        
        for y in range(grid_size, height, grid_size):
            line = SubElement(svg, 'line')
            line.set('x1', '0')
            line.set('y1', str(y))
            line.set('x2', str(width))
            line.set('y2', str(y))
            line.set('stroke', '#FFFFFF')
            line.set('stroke-width', '0.3')
            line.set('opacity', str(opacity))

    def add_corner_details(self, svg, width, height):
        """Add subtle corner accent lines"""
        corner_size = random.randint(30, 50)
        
        # Top-left
        polyline = SubElement(svg, 'polyline')
        polyline.set('points', f"0,{corner_size} 0,0 {corner_size},0")
        polyline.set('stroke', self.colors['roads'])
        polyline.set('stroke-width', '2')
        polyline.set('fill', 'none')
        polyline.set('opacity', '0.7')

        # Bottom-right
        polyline = SubElement(svg, 'polyline')
        polyline.set('points', f"{width-corner_size},{height} {width},{height} {width},{height-corner_size}")
        polyline.set('stroke', self.colors['roads'])
        polyline.set('stroke-width', '2')
        polyline.set('fill', 'none')
        polyline.set('opacity', '0.7')

    def create_svg_panel(self, location_name, width=1200, height=800, variation=0, meters_per_pixel=20):
        """Generate SVG panel with debug output"""
        if location_name not in self.locations:
            print(f"  Warning: Location {location_name} not found")
            return None
            
        center_lat, center_lon = self.locations[location_name]
        
        # Add variation to center point
        random.seed(hash(location_name + str(variation)))
        offset_meters = 300  # Smaller offset
        lat_offset = (offset_meters * random.uniform(-1, 1)) / 111000.0
        lon_offset = (offset_meters * random.uniform(-1, 1)) / (111000.0 * math.cos(math.radians(center_lat)))
        
        center_lat += lat_offset
        center_lon += lon_offset
        
        # Fetch data using scale-based bounds
        roads_data, contours_data, bounds = self.fetch_map_data(center_lat, center_lon, width, height, meters_per_pixel)
        
        # Create SVG
        svg = Element('svg')
        svg.set('width', str(width))
        svg.set('height', str(height))
        svg.set('xmlns', 'http://www.w3.org/2000/svg')
        svg.set('viewBox', f'0 0 {width} {height}')
        
        # Background
        bg = SubElement(svg, 'rect')
        bg.set('width', str(width))
        bg.set('height', str(height))
        bg.set('fill', self.colors['background'])
        
        # Create coordinate conversion using the exact calculated bounds
        min_lat = bounds['min_lat']
        max_lat = bounds['max_lat']
        min_lon = bounds['min_lon']
        max_lon = bounds['max_lon']
        
        print(f"  Coordinate system bounds:")
        print(f"    Lat: {min_lat:.6f} to {max_lat:.6f} (range: {max_lat-min_lat:.6f})")
        print(f"    Lon: {min_lon:.6f} to {max_lon:.6f} (range: {max_lon-min_lon:.6f})")
        
        def coord_to_svg(lat, lon):
            # Direct linear mapping from geographic bounds to pixel coordinates
            x = ((lon - min_lon) / (max_lon - min_lon)) * width
            y = height - ((lat - min_lat) / (max_lat - min_lat)) * height
            return x, y
        
        contour_count = 0
        road_count = 0
        
        # Debug: Test coordinate conversion
        test_lat, test_lon = (min_lat + max_lat) / 2, (min_lon + max_lon) / 2
        test_x, test_y = coord_to_svg(test_lat, test_lon)
        print(f"  Coordinate test: center ({test_lat:.6f}, {test_lon:.6f}) -> ({test_x:.1f}, {test_y:.1f})")
        
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
                    polyline.set('stroke-width', str(random.uniform(1.2, 2.0)))
                    polyline.set('fill', 'none')
                    polyline.set('opacity', '0.8')
                    polyline.set('stroke-linecap', 'round')
                    contour_count += 1
        
        # Generate synthetic contours using same bounds and coordinate system
        print("  Adding synthetic contours...")
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
                polyline.set('stroke-width', str(random.uniform(0.8, 1.4)))
                polyline.set('fill', 'none')
                polyline.set('opacity', str(contour['opacity']))
                polyline.set('stroke-linecap', 'round')
                contour_count += 1
        
        # Draw roads using the same coordinate system  
        road_sample_coords = []
        for element in roads_data.get('elements', []):
            if 'geometry' in element and len(element['geometry']) > 1:
                highway_type = element.get('tags', {}).get('highway', '')
                
                # Simple road widths (back to original)
                width_map = {
                    'motorway': 6,
                    'motorway_link': 4,
                    'trunk': 5,
                    'trunk_link': 3.5,
                    'primary': 4,
                    'primary_link': 2.5,
                    'secondary': 3,
                    'secondary_link': 2,
                    'tertiary': 2.5,
                    'tertiary_link': 2,
                    'residential': 2,
                    'unclassified': 1.5,
                    'service': 1.2,
                    'living_street': 1.8
                }
                stroke_width = width_map.get(highway_type, 1.5)
                
                points = []
                for coord in element['geometry']:
                    x, y = coord_to_svg(coord['lat'], coord['lon'])
                    points.append(f"{x:.1f},{y:.1f}")
                    # Sample some coordinates for debugging
                    if len(road_sample_coords) < 3:
                        road_sample_coords.append((coord['lat'], coord['lon'], x, y))
                
                if len(points) > 1:
                    polyline = SubElement(svg, 'polyline')
                    polyline.set('points', ' '.join(points))
                    polyline.set('stroke', self.colors['roads'])
                    polyline.set('stroke-width', str(stroke_width))
                    polyline.set('fill', 'none')
                    polyline.set('stroke-linecap', 'round')
                    polyline.set('stroke-linejoin', 'round')
                    road_count += 1
        
        # Debug: Show sample road coordinates
        for i, (lat, lon, x, y) in enumerate(road_sample_coords):
            print(f"  Road sample {i}: ({lat:.6f}, {lon:.6f}) -> ({x:.1f}, {y:.1f})")
        
        print(f"  Added {road_count} roads and {contour_count} contours")
        
        # Add decorative overlays
        if variation % 3 == 0:
            self.add_subtle_grid(svg, width, height)
        
        if variation % 4 == 0:
            self.add_corner_details(svg, width, height)
        
        return svg

    def generate_panels(self, count=8, width=1200, height=800, meters_per_pixel=20):
        """Generate panels using consistent scale"""
        panels = []
        locations = list(self.locations.keys())
        
        print(f"Generating {count} panels...")
        print(f"Panel size: {width}x{height}px at {meters_per_pixel}m/pixel")
        print(f"Real-world coverage: {width*meters_per_pixel}m × {height*meters_per_pixel}m")
        print(f"Locations: {', '.join([loc.replace('_', ' ').title() for loc in locations])}")
        print("-" * 60)
        
        for i in range(count):
            location = locations[i % len(locations)]
            variation = i // len(locations)
            
            print(f"Panel {i+1}/{count}: {location.replace('_', ' ').title()} (variation {variation})")
            
            svg = self.create_svg_panel(location, width, height, variation, meters_per_pixel)
            if svg is not None:
                panels.append({
                    'location': location,
                    'variation': variation,
                    'svg': svg
                })
                print("  ✓ Panel generated successfully")
            else:
                print("  ✗ Failed to generate panel")
            print()
        
        return panels

    def save_panels(self, panels, output_dir="vinyl_panels"):
        """Save SVG panels to files"""
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"Saving panels to '{output_dir}' directory...")
        print("-" * 60)
        
        for i, panel in enumerate(panels):
            filename = f"panel_{i+1:02d}_{panel['location']}_v{panel['variation']}.svg"
            filepath = os.path.join(output_dir, filename)
            
            rough_string = tostring(panel['svg'], 'unicode')
            reparsed = minidom.parseString(rough_string)
            pretty = reparsed.toprettyxml(indent="  ")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(pretty)
            
            print(f"✓ Saved: {filename}")
        
        print(f"\n🎉 All {len(panels)} panels saved successfully!")
        print(f"📁 Location: {os.path.abspath(output_dir)}")

def main():
    """Main function"""
    print("=" * 70)
    print("🚗 SELF-DRIVING CAR LAB - VINYL PANEL GENERATOR")
    print("=" * 70)
    print("DEBUG: Added coordinate system debugging")
    print(f"Colors: Roads(#FFB81C) | Background(#071B2C) | Contours(#FFFFFF)")
    print()
    
    generator = MapArtGenerator()
    
    try:
        # Generate panels with debugging enabled
        panels = generator.generate_panels(count=8, width=1200, height=800, meters_per_pixel=20)
        
        if panels:
            generator.save_panels(panels)
            print(f"\n📋 SUMMARY:")
            print(f"   Panels generated: {len(panels)}")
            print(f"   Check console output for coordinate debugging info")
            print(f"   Ready for vinyl printing! 🎯")
        else:
            print("❌ No panels generated")
            
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
