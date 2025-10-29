<?xml version="1.0" encoding="UTF-8"?><sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>precip_anomaly</sld:Name>
    <sld:UserStyle>
      <sld:Name>precip_anomaly</sld:Name>
      <sld:Title>Precipitation Anomaly Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#4a2b1d" quantity="-200"/>
              <sld:ColorMapEntry color="#4a2b1d" quantity="-100"/>
              <sld:ColorMapEntry color="#804a32" quantity="-80"/>
              <sld:ColorMapEntry color="#ac6235" quantity="-60"/>
              <sld:ColorMapEntry color="#cc8654" quantity="-40"/>
              <sld:ColorMapEntry color="#d6a785" quantity="-30"/>
              <sld:ColorMapEntry color="#edd2bf" quantity="-20"/>
              <sld:ColorMapEntry color="#ffffff" quantity="-10"/>
              <sld:ColorMapEntry color="#ffffff" quantity="10"/>
              <sld:ColorMapEntry color="#d0f5d0" quantity="20"/>
              <sld:ColorMapEntry color="#9ce69c" quantity="30"/>
              <sld:ColorMapEntry color="#4fe34f" quantity="40"/>
              <sld:ColorMapEntry color="#35a135" quantity="60"/>
              <sld:ColorMapEntry color="#005500" quantity="80"/>
              <sld:ColorMapEntry color="#003d00" quantity="100"/>
              <sld:ColorMapEntry color="#003d00" quantity="200"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
