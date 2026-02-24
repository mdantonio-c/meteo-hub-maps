<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld"
                           xmlns="http://www.opengis.net/sld"
                           xmlns:gml="http://www.opengis.net/gml"
                           xmlns:ogc="http://www.opengis.net/ogc"
                           version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>sf_1_3</sld:Name>
    <sld:UserStyle>
      <sld:Name>sf_1_3</sld:Name>
      <sld:Title>SF 1 3 Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#3f5736" quantity="0.1" opacity="0"/>
              <sld:ColorMapEntry color="#3f5736" quantity="0.5" />
              <sld:ColorMapEntry color="#4d7e3a" quantity="1"/>
              <sld:ColorMapEntry color="#89bf73" quantity="2"/>
              <sld:ColorMapEntry color="#A3A3A3" quantity="5"/>
              <sld:ColorMapEntry color="#C2C2C2" quantity="10"/>
              <sld:ColorMapEntry color="#e0e0e0" quantity="15"/>
              <sld:ColorMapEntry color="#c398a6" quantity="20"/>
              <sld:ColorMapEntry color="#ac7283" quantity="30"/>
              <sld:ColorMapEntry color="#80115b" quantity="50"/>
              <sld:ColorMapEntry color="#530a4d" quantity="100"/>
              <sld:ColorMapEntry color="#684f05" quantity="1000"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
