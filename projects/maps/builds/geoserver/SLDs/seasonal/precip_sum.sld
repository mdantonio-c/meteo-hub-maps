<?xml version="1.0" encoding="UTF-8"?><sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>precip_sum</sld:Name>
    <sld:UserStyle>
      <sld:Name>precip_sum</sld:Name>
      <sld:Title>Precipitation Sum Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#FFFFFF" quantity="0"/>
              <sld:ColorMapEntry color="#E6F3FF" quantity="10"/>
              <sld:ColorMapEntry color="#CCE7FF" quantity="20"/>
              <sld:ColorMapEntry color="#99D6FF" quantity="40"/>
              <sld:ColorMapEntry color="#66C2FF" quantity="60"/>
              <sld:ColorMapEntry color="#33ADFF" quantity="80"/>
              <sld:ColorMapEntry color="#0099FF" quantity="100"/>
              <sld:ColorMapEntry color="#0080CC" quantity="150"/>
              <sld:ColorMapEntry color="#006699" quantity="200"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>