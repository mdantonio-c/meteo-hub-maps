<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld"
                           xmlns="http://www.opengis.net/sld"
                           xmlns:gml="http://www.opengis.net/gml"
                           xmlns:ogc="http://www.opengis.net/ogc"
                           version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>radar-sri</sld:Name>
    <sld:UserStyle>
      <sld:Name>radar-sri</sld:Name>
      <sld:Title>Radar SRI (Surface Rainfall Intensity)</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
                <sld:ColorMapEntry color="#a6a0a0" opacity="0.3" quantity="0.1"/>
              <sld:ColorMapEntry color="#a3f5e3" quantity="1"/>
              <sld:ColorMapEntry color="#1ae4b7" quantity="2"/>
              <sld:ColorMapEntry color="#2dbf00" quantity="5"/>
		       <sld:ColorMapEntry color="#baeb09" quantity="10"/>
              <sld:ColorMapEntry color="#ebe300" quantity="15"/>
              <sld:ColorMapEntry color="#febf00" quantity="20"/>
              <sld:ColorMapEntry color="#f56200" quantity="30"/>
              <sld:ColorMapEntry color="#ff3e3b" quantity="50"/>
              <sld:ColorMapEntry color="#ff0000" quantity="75"/>
              <sld:ColorMapEntry color="#fc0599" quantity="100"/>
              <sld:ColorMapEntry color="#f75dfc" quantity="500"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
