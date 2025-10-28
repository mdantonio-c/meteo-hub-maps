<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>mcc</sld:Name>
    <sld:UserStyle>
      <sld:Name>mcc</sld:Name>
      <sld:Title>MCC Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#fafafd" quantity="50" opacity="0"/>
              <sld:ColorMapEntry color="#ececf7" quantity="60"/>
              <sld:ColorMapEntry color="#d8d7ee" quantity="70"/>
              <sld:ColorMapEntry color="#c4c5e6" quantity="80"/>
              <sld:ColorMapEntry color="#b0b2dd" quantity="90"/>
              <sld:ColorMapEntry color="#9fa1d5" quantity="100"/>
              <sld:ColorMapEntry color="#9fa1d5" quantity="200"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
