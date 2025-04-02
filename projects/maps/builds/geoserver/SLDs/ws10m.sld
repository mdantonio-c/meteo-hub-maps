<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>ws10m</sld:Name>
    <sld:UserStyle>
      <sld:Name>ws10m</sld:Name>
      <sld:Title>WS10M Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#8bd8f9" quantity="1"/>
              <sld:ColorMapEntry color="#7070ff" quantity="2"/>
              <sld:ColorMapEntry color="#4bcf4f" quantity="5"/>
              <sld:ColorMapEntry color="#ffff00" quantity="10"/>
              <sld:ColorMapEntry color="#fec601" quantity="20"/>
              <sld:ColorMapEntry color="#ff3333" quantity="30"/>
              <sld:ColorMapEntry color="#ee82ee" quantity="50"/>
              <sld:ColorMapEntry color="#ff00c3" quantity="70"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
