<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor
    xmlns:sld="http://www.opengis.net/sld"
    xmlns="http://www.opengis.net/sld"
    xmlns:gml="http://www.opengis.net/gml"
    xmlns:ogc="http://www.opengis.net/ogc"
    version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>custom_marine_product</sld:Name>
    <sld:UserStyle>
      <sld:Name>custom_marine_product</sld:Name>
      <sld:Title>ww3 t01</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>raster_style</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#B9E3F3" quantity="1"/>
              <sld:ColorMapEntry color="#7BBBD6" quantity="2"/>
              <sld:ColorMapEntry color="#005CB8" quantity="3"/>
              <sld:ColorMapEntry color="#09DE5B" quantity="4"/>
		       <sld:ColorMapEntry color="#00945C" quantity="5"/>
              <sld:ColorMapEntry color="#FFFF00" quantity="6"/>
              <sld:ColorMapEntry color="#FFA500" quantity="7"/>
              <sld:ColorMapEntry color="#FF0000" quantity="8"/>
              <sld:ColorMapEntry color="#FD089F" quantity="9"/>
              <sld:ColorMapEntry color="#B922C7" quantity="10"/>
              <sld:ColorMapEntry color="#611269" quantity="12"/>
              <sld:ColorMapEntry color="#5C615C" quantity="14"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
