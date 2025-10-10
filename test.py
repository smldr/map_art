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
            'contours': '#FFFFFF'
        }
        
        # ALL locations from your KML file + Port Elizabeth overview
        # ALL locations from your KML file + Port Elizabeth overview + Berlin
        self.locations = {
            'nmu': (-34.00580646599881, 25.67395371405373),
            'bird_street': (-33.964810953176, 25.61665967430209),
            'missionvale': (-33.87267758344066, 25.55332899427664),
            'george': (-33.96092976771337, 22.53428843644683),
            'port_elizabeth_overview': (-33.98, 25.55),
            'berlin': (48.08, 11.638333),  # 48°04'48"N 11°38'17"E
            'aachen': (50.777222, 6.0775)  # 50°46'38"N 6°04'39"E
        }

    def load_compass_svg(self, compass_file_path="cpm-lab-nmu-round.svg"):
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
        """Add scaled compass in CENTER of the image - DOUBLED SIZE"""
        if compass_svg is None:
            return
            
        compass_size = int(border_width * 2.6)  # Doubled from 0.8 to 1.6
        
        # Position in CENTER of the image
        compass_x = (total_width - compass_size) // 2
        compass_y = (total_height - compass_size) // 2
        
        print(f"  Adding compass: {compass_size}×{compass_size}px at CENTER ({compass_x}, {compass_y}) [DOUBLED SIZE]")
        
        compass_group = SubElement(svg, 'g')
        compass_group.set('transform', f'translate({compass_x}, {compass_y}) scale({compass_size/1440})')
        
        for child in compass_svg:
            compass_group.append(child)

    def calculate_bounds_from_scale(self, center_lat, center_lon, width_px, height_px, meters_per_pixel=8):
        """Calculate geographic bounds based on image dimensions and scale"""
        width_meters = width_px * meters_per_pixel
        height_meters = height_px * meters_per_pixel
        
        lat_degrees_per_meter = 1.0 / 111000.0
        lon_degrees_per_meter = 1.0 / (111000.0 * math.cos(math.radians(center_lat)))
        
        half_height_deg = (height_meters / 2) * lat_degrees_per_meter
        half_width_deg = (width_meters / 2) * lon_degrees_per_meter
        
        bounds = {
            'min_lat': center_lat - half_height_deg,
            'max_lat': center_lat + half_height_deg,
            'min_lon': center_lon - half_width_deg,
            'max_lon': center_lon + half_width_deg
        }
        
        return bounds

    def fetch_map_data(self, center_lat, center_lon, width_px, height_px, meters_per_pixel=8, major_roads_only=False):
        """Fetch road and contour data using calculated bounds"""
        overpass_url = "http://overpass-api.de/api/interpreter"
        bounds = self.calculate_bounds_from_scale(center_lat, center_lon, width_px, height_px, meters_per_pixel)
        
        print(f"  Coverage: {width_px * meters_per_pixel}m × {height_px * meters_per_pixel}m at {meters_per_pixel}m/px")
        
        if major_roads_only:
            road_types = "motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link"
            print("  Fetching major roads only")
        else:
            road_types = "motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|residential|unclassified|service|living_street"
            print("  Fetching all road types")
        
        road_query = f"""
        [out:json][timeout:30];
        (
          way["highway"~"^({road_types})$"]
             ({bounds['min_lat']},{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']});
        );
        out geom;
        """
        
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

    def create_svg_panel(self, location_name, compass_svg, width=600, height=1350, border_width=50, variation=0, meters_per_pixel=8):
        """Generate clean SVG panel with centered compass"""
        if location_name not in self.locations:
            print(f"  Warning: Location {location_name} not found")
            return None
            
        center_lat, center_lon = self.locations[location_name]
        
        is_overview = location_name == 'port_elizabeth_overview'
        
        if is_overview:
            meters_per_pixel = 50
            print(f"  Overview panel - using {meters_per_pixel}m/px scale")
        
        total_width = width + (2 * border_width)
        total_height = height + (2 * border_width)
        content_width = width
        content_height = height
        
        print(f"  Panel: {total_width}×{total_height}px (content: {content_width}×{content_height}px)")
        
        # Add variation
        random.seed(hash(location_name + str(variation)))
        offset_meters = 500 if is_overview else 150
        lat_offset = (offset_meters * random.uniform(-1, 1)) / 111000.0
        lon_offset = (offset_meters * random.uniform(-1, 1)) / (111000.0 * math.cos(math.radians(center_lat)))
        
        center_lat += lat_offset
        center_lon += lon_offset
        
        roads_data, contours_data, bounds = self.fetch_map_data(
            center_lat, center_lon, content_width, content_height, 
            meters_per_pixel, major_roads_only=is_overview
        )
        
        # Create SVG - simple and clean
        svg = Element('svg')
        svg.set('width', str(total_width))
        svg.set('height', str(total_height))
        svg.set('xmlns', 'http://www.w3.org/2000/svg')
        svg.set('viewBox', f'0 0 {total_width} {total_height}')
        
        # Single background color throughout - no border color difference
        bg = SubElement(svg, 'rect')
        bg.set('width', str(total_width))
        bg.set('height', str(total_height))
        bg.set('fill', self.colors['background'])
        
        # Coordinate conversion for content area
        min_lat = bounds['min_lat']
        max_lat = bounds['max_lat']
        min_lon = bounds['min_lon']
        max_lon = bounds['max_lon']
        
        def coord_to_svg(lat, lon):
            x = border_width + ((lon - min_lon) / (max_lon - min_lon)) * content_width
            y = border_width + content_height - ((lat - min_lat) / (max_lat - min_lat)) * content_height
            return x, y
        
        contour_count = 0
        road_count = 0
        
        # Draw ONLY real contours - no synthetic ones
        for element in contours_data.get('elements', []):
            if 'geometry' in element and len(element['geometry']) > 1:
                points = []
                for coord in element['geometry']:
                    x, y = coord_to_svg(coord['lat'], coord['lon'])
                    points.append(f"{x:.1f},{y:.1f}")
                
                if len(points) > 1:
                    stroke_width = 2.5 if is_overview else random.uniform(1.2, 2.0)
                    polyline = SubElement(svg, 'polyline')
                    polyline.set('points', ' '.join(points))
                    polyline.set('stroke', self.colors['contours'])
                    polyline.set('stroke-width', str(stroke_width))
                    polyline.set('fill', 'none')
                    polyline.set('opacity', '0.8')
                    polyline.set('stroke-linecap', 'round')
                    contour_count += 1
        
        # Draw roads
        for element in roads_data.get('elements', []):
            if 'geometry' in element and len(element['geometry']) > 1:
                highway_type = element.get('tags', {}).get('highway', '')
                
                if is_overview:
                    width_map = {
                        'motorway': 10, 'motorway_link': 7,
                        'trunk': 8, 'trunk_link': 6,
                        'primary': 6, 'primary_link': 4.5,
                        'secondary': 4, 'secondary_link': 3
                    }
                else:
                    width_map = {
                        'motorway': 4, 'motorway_link': 3,
                        'trunk': 3.5, 'trunk_link': 2.5,
                        'primary': 3, 'primary_link': 2,
                        'secondary': 2.5, 'secondary_link': 1.8,
                        'tertiary': 2, 'tertiary_link': 1.5,
                        'residential': 1.5, 'unclassified': 1.2,
                        'service': 0.8, 'living_street': 1.2
                    }
                
                stroke_width = width_map.get(highway_type, 2 if is_overview else 1.0)
                
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
        
        print(f"  Added {road_count} roads and {contour_count} genuine contours only")
        
        # Add CENTERED compass with doubled size
        self.add_compass_to_content(svg, compass_svg, border_width, total_width, total_height)
        
        return svg

    def generate_panels(self, count=12, width=600, height=1350, border_width=50, meters_per_pixel=8):
        """Generate clean door-shaped panels with centered compass"""
        panels = []
        locations = list(self.locations.keys())
        
        print("Loading compass SVG...")
        compass_svg = self.load_compass_svg("cpm-lab-nmu-round.svg")
        if compass_svg is not None:
            print("✓ Compass SVG loaded successfully")
        else:
            print("⚠ Compass SVG not found - panels will be generated without compass")
        
        total_width = width + (2 * border_width)
        total_height = height + (2 * border_width)
        
        print(f"\nGenerating {count} clean door panels with CENTERED compass...")
        print(f"🚪 Size: {total_width}×{total_height}px")
        print(f"🧭 Compass: {int(border_width * 2.6)}×{int(border_width * 2.6)}px (DOUBLED SIZE, CENTERED)")
        print(f"📍 Locations: {', '.join([loc.replace('_', ' ').title() for loc in locations])}")
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
                print("  ✓ Panel with centered compass generated")
            else:
                print("  ✗ Failed to generate panel")
            print()
        
        return panels

    def save_panels(self, panels, output_dir="door_panels_centered_compass"):
        """Save clean SVG panels to files"""
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"Saving door panels with centered compass to '{output_dir}' directory...")
        print("-" * 60)
        
        for i, panel in enumerate(panels):
            filename = f"door_panel_{i+1:02d}_{panel['location']}_v{panel['variation']}.svg"
            filepath = os.path.join(output_dir, filename)
            
            rough_string = tostring(panel['svg'], 'unicode')
            reparsed = minidom.parseString(rough_string)
            pretty = reparsed.toprettyxml(indent="  ")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(pretty)
            
            print(f"✓ Saved: {filename}")
        
        print(f"\n🎉 All {len(panels)} panels with centered compass saved!")
        print(f"📁 Location: {os.path.abspath(output_dir)}")

def main():
    """Main function"""
    print("=" * 70)
    print("🚗 SELF-DRIVING CAR LAB - CENTERED COMPASS DOOR PANELS")
    print("=" * 70)
    print("🧭 Compass size DOUBLED and CENTERED on each panel")
    print("✨ Clean design with only genuine map data")
    print(f"Colors: Roads(#FFB81C) | Background(#071B2C) | Contours(#FFFFFF)")
    print()
    
    generator = MapArtGenerator()
    
    try:
        panels = generator.generate_panels(
            count=12,
            width=600,
            height=1350,
            border_width=50,
            meters_per_pixel=8
        )
        
        if panels:
            generator.save_panels(panels)
            print(f"\n📋 SUMMARY:")
            print(f"   🚪 Door panels: {len(panels)}")
            print(f"   🧭 Compass: {int(50 * 2.6)}×{int(50 * 2.6)}px (doubled and centered)")
            print(f"   ✨ Clean design with centered compass overlay")
            print(f"   ✅ Ready for vinyl printing!")
        else:
            print("❌ No panels generated")
            
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
