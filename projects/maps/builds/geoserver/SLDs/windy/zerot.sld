<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>zerot</sld:Name>
    <sld:UserStyle>
      <sld:Name>zerot</sld:Name>
      <sld:Title>Zero T Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#fafdf9" quantity="50" opacity="0"/>
              <sld:ColorMapEntry color="#ecf7ea" quantity="60"/>
              <sld:ColorMapEntry color="#d6eed4" quantity="70"/>
              <sld:ColorMapEntry color="#c4e6c0" quantity="80"/>
              <sld:ColorMapEntry color="#b0deab" quantity="90"/>
              <sld:ColorMapEntry color="#9dd797" quantity="100"/>
              <sld:ColorMapEntry color="#9dd797" quantity="200"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
