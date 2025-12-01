# Tiles Data Documentation

This document describes the tile map data serving architecture for multi-layer forecast maps.

## Overview

Tile maps provide pre-rendered forecast map tiles in a standard web map tile format (XYZ or TMS). Unlike dynamic WMS layers, tiles are static files served directly by nginx for optimal performance.

## Supported Datasets

Same datasets as Windy data:

| Dataset | Area | Coverage | Forecast Length |
|---------|------|----------|-----------------|
| `lm2.2` | Italia | 34.5°-48.0°N, 5.0°-21.2°E | 0-48h |
| `lm5` | Area Mediterranea | 25.8°-55.5°N, -30.9°-47.0°E | 0-72h |
| `iff` | Italia | 34.5°-48.0°N, 5.0°-21.2°E | 6-72h (3h step) |
| `icon` | Italia | 33.69°-48.91°N, 2.99°-22.01°E | 0-72h |

## Data Structure

### File System Organization

```
/<platform>/<env>/Tiles-<run>-<dataset>.web/
└── <area>/
    ├── <reftime>.READY
    └── <zoom>/
        └── <x>/
            └── <y>.png
```

**Example:**
```
/G100/PROD/Tiles-00-lm2.2.web/
└── Italia/
    ├── 2025120100.READY
    └── 7/
        └── 67/
            ├── 45.png
            ├── 46.png
            └── ...
```

### Tile Naming Convention

Follows standard web map tile format:
- **Zoom Level:** `<z>` (typically 0-12)
- **Column:** `<x>`
- **Row:** `<y>`
- **Format:** PNG images

## Nginx Configuration

Tiles are served as static files by nginx, external to the Python API.

### Example Nginx Configuration

```nginx
server {
    location /tiles/00-lm2.2/ {
        alias /path/to/data/G100/PROD/Tiles-00-lm2.2.web/Italia/;
        
        # Enable CORS for map libraries
        add_header Access-Control-Allow-Origin *;
        
        # Cache tiles
        expires 1h;
        add_header Cache-Control "public, immutable";
    }
    
    location /tiles/12-lm2.2/ {
        alias /path/to/data/G100/PROD/Tiles-12-lm2.2.web/Italia/;
        add_header Access-Control-Allow-Origin *;
        expires 1h;
    }
    
    location /tiles/00-lm5/ {
        alias /path/to/data/G100/PROD/Tiles-00-lm5.web/Area_Mediterranea/;
        add_header Access-Control-Allow-Origin *;
        expires 1h;
    }
    
    location /tiles/12-lm5/ {
        alias /path/to/data/G100/PROD/Tiles-12-lm5.web/Area_Mediterranea/;
        add_header Access-Control-Allow-Origin *;
        expires 1h;
    }
}
```

### URL Pattern

```
http://<server>/tiles/<run>-<dataset>/<z>/<x>/<y>.png
```

**Example:**
```
http://server/tiles/00-lm2.2/7/67/45.png
```

## API Access

### Get Tiles Reference Time

The API provides metadata about available tile sets:

```bash
GET /api/tiles?dataset=lm2.2
```

**Response:**
```json
{
  "dataset": "lm2.2",
  "area": "Italia",
  "start_offset": 0,
  "end_offset": 48,
  "step": 1,
  "boundaries": {
    "SW": [34.5, 5.0],
    "NE": [48.0, 21.2]
  },
  "reftime": "2025120100",
  "platform": null
}
```

### Get Latest Run

Without specifying a run, returns the most recent available:

```bash
GET /api/tiles?dataset=lm5
```

### Specify Run

```bash
GET /api/tiles?dataset=lm5&run=12
```

## Integration with Map Libraries

### Leaflet

```javascript
// Get tile metadata
fetch('/api/tiles?dataset=lm2.2')
  .then(response => response.json())
  .then(data => {
    const reftime = data.reftime;
    const bounds = [
      [data.boundaries.SW[0], data.boundaries.SW[1]],
      [data.boundaries.NE[0], data.boundaries.NE[1]]
    ];
    
    // Add tile layer
    const tileLayer = L.tileLayer(
      'http://server/tiles/00-lm2.2/{z}/{x}/{y}.png',
      {
        attribution: `Forecast: ${reftime}`,
        bounds: bounds,
        minZoom: 5,
        maxZoom: 12
      }
    );
    
    map.addLayer(tileLayer);
  });
```

### OpenLayers

```javascript
import TileLayer from 'ol/layer/Tile';
import XYZ from 'ol/source/XYZ';

// Get tile metadata
const response = await fetch('/api/tiles?dataset=lm5');
const data = await response.json();

const tileLayer = new TileLayer({
  source: new XYZ({
    url: 'http://server/tiles/00-lm5/{z}/{x}/{y}.png',
    crossOrigin: 'anonymous'
  }),
  extent: [
    data.boundaries.SW[1], data.boundaries.SW[0],
    data.boundaries.NE[1], data.boundaries.NE[0]
  ]
});

map.addLayer(tileLayer);
```

### Mapbox GL JS

```javascript
// Get tile metadata
const response = await fetch('/api/tiles?dataset=icon');
const data = await response.json();

map.addSource('forecast-tiles', {
  type: 'raster',
  tiles: ['http://server/tiles/00-icon/{z}/{x}/{y}.png'],
  tileSize: 256,
  bounds: [
    data.boundaries.SW[1],
    data.boundaries.SW[0],
    data.boundaries.NE[1],
    data.boundaries.NE[0]
  ]
});

map.addLayer({
  id: 'forecast-layer',
  type: 'raster',
  source: 'forecast-tiles',
  paint: {
    'raster-opacity': 0.8
  }
});
```

## Time-Based Tiles

For animated forecasts with time offsets:

### Directory Structure

```
/Tiles-00-lm2.2.web/Italia/
├── 2025120100.READY
├── t2m/
│   ├── 0000/  # Forecast hour 0
│   │   └── 7/
│   │       └── 67/
│   │           └── 45.png
│   ├── 0001/  # Forecast hour 1
│   │   └── 7/
│   │       └── ...
│   └── ...
└── prec6/
    └── ...
```

### URL Pattern

```
http://<server>/tiles/<run>-<dataset>/<variable>/<offset>/<z>/<x>/<y>.png
```

### Animation Example

```javascript
class ForecastAnimation {
  constructor(map, dataset, variable, run) {
    this.map = map;
    this.dataset = dataset;
    this.variable = variable;
    this.run = run;
    this.currentOffset = 0;
    this.layer = null;
  }
  
  async init() {
    // Get metadata
    const response = await fetch(`/api/tiles?dataset=${this.dataset}&run=${this.run}`);
    const data = await response.json();
    
    this.maxOffset = data.end_offset;
    this.updateLayer();
  }
  
  updateLayer() {
    if (this.layer) {
      this.map.removeLayer(this.layer);
    }
    
    const offset = String(this.currentOffset).padStart(4, '0');
    const url = `http://server/tiles/${this.run}-${this.dataset}/${this.variable}/${offset}/{z}/{x}/{y}.png`;
    
    this.layer = L.tileLayer(url);
    this.map.addLayer(this.layer);
  }
  
  animate() {
    setInterval(() => {
      this.currentOffset = (this.currentOffset + 1) % (this.maxOffset + 1);
      this.updateLayer();
    }, 500); // Update every 500ms
  }
}

// Usage
const animation = new ForecastAnimation(map, 'lm2.2', 't2m', '00');
animation.init().then(() => animation.animate());
```

## Performance Considerations

### Advantages of Static Tiles

- **Fast Delivery:** Direct file serving by nginx
- **Scalable:** Easy to cache and CDN-enable
- **Client Performance:** Pre-rendered, no client-side rendering needed
- **Bandwidth:** Efficient for mobile clients

### Caching Strategy

```nginx
# Aggressive caching for tiles
location /tiles/ {
    expires 1h;
    add_header Cache-Control "public, immutable";
    
    # Enable gzip compression
    gzip on;
    gzip_types image/png;
}
```

### CDN Integration

Tiles can be easily served through a CDN:

1. Configure nginx to serve tiles
2. Point CDN to tile URLs
3. Set appropriate cache headers
4. Update client applications to use CDN URLs

## Operational Notes

### Data Updates

- New tile sets generated with each forecast run
- `.READY` file indicates tiles are complete
- Old tiles can be archived or removed after new runs

### Storage Requirements

- Each tile set can be several GB depending on:
  - Number of zoom levels
  - Number of variables
  - Number of time steps
  - Tile dimensions and compression

### Monitoring

Check for new tiles:

```bash
# Find latest .READY file
find /data -name "*.READY" -path "*/Tiles-*" -type f -printf '%T@ %p\n' | sort -n | tail -1
```

## Troubleshooting

### Tiles Not Loading

1. Check nginx configuration and file paths
2. Verify `.READY` file exists
3. Test direct file access: `curl http://server/tiles/00-lm2.2/7/67/45.png`
4. Check CORS headers if loading from different domain
5. Verify directory permissions

### Incorrect Tile Bounds

1. Check API response for boundary coordinates
2. Verify map library extent configuration
3. Ensure coordinate system matches (EPSG:4326 vs EPSG:3857)

### Missing Time Offsets

1. Verify all offset directories exist
2. Check tile generation process completed successfully
3. Review logs for incomplete tile sets
