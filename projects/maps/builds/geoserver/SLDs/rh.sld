<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>rh</sld:Name>
    <sld:UserStyle>
      <sld:Name>rh</sld:Name>
      <sld:Title>RH Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#ff0000" quantity="20"/>
              <sld:ColorMapEntry color="#ff8c00" quantity="40"/>
              <sld:ColorMapEntry color="#ffff00" quantity="60"/>
              <sld:ColorMapEntry color="#00ff00" quantity="80"/>
              <sld:ColorMapEntry color="#00ffff" quantity="90"/>
              <sld:ColorMapEntry color="#0000ff" quantity="100"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
