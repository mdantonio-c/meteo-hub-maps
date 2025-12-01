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
              <sld:ColorMapEntry color="#c7ecff" quantity="0.1"/>
              <sld:ColorMapEntry color="#acfce6" quantity="1"/>
              <sld:ColorMapEntry color="#2af5bb" quantity="5"/>
              <sld:ColorMapEntry color="#64ff61" quantity="10"/>
              <sld:ColorMapEntry color="#8ce614" quantity="20"/>
              <sld:ColorMapEntry color="#fff700" quantity="30"/>
              <sld:ColorMapEntry color="#f76300" quantity="50"/>
              <sld:ColorMapEntry color="#ff1929" quantity="75"/>
              <sld:ColorMapEntry color="#fc0591" quantity="100"/>
              <sld:ColorMapEntry color="#f75dfc" quantity="500"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
