# Offline Earth map data

The globe texture uses the bundled Natural Earth **1:110m Admin 0 Countries** GeoJSON (`earth_countries.geojson`). The source contains 177 polygon/multipolygon features in longitude/latitude coordinates. Natural Earth states that its raster and vector datasets are public domain: [Natural Earth terms of use](https://www.naturalearthdata.com/about/terms-of-use/). Source data information and downloadable 1:110m layers are listed on [Natural Earth's 1:110m physical vectors page](https://www.naturalearthdata.com/downloads/110m-physical-vectors/).

The GeoJSON was retrieved from the `nvkelso/natural-earth-vector` GeoJSON mirror, file `geojson/ne_110m_admin_0_countries.geojson`. Its bundled-file SHA-256 is:

```text
6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f
```

`assets/earth_texture.png` is a locally generated 1440×720 equirectangular texture with ocean fill, land polygons, coastlines, and country borders. Rebuild it from the bundled source with:

```bash
python scripts/build_earth_texture.py
```

The dashboard projects this texture onto an orthographic sphere in Canvas. It also overlays coordinate graticules and approximate ocean/sea labels. This is a global-scale reference map; 1:110m geometry is generalized and is not suitable for navigation, boundary adjudication, or local flood delineation. Flood markers use the source dataset's representative geocodes and are visually distinct from satellite scene centers and river-grid cells.

The texture is served locally by the project API. No paid key, remote tile service, or runtime external network request is required.

The globe also has a Chennai quick-select/reference label at 13.0827°N, 80.2707°E, based on the [OpenStreetMap Chennai place reference](https://wiki.openstreetmap.org/wiki/Chennai). It is only a location shortcut for coordinate queries; it is not a flood observation, a city boundary, or a forecast result. Other places can be selected by map click or latitude/longitude entry; there is no global place-name geocoder.
