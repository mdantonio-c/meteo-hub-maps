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
      <sld:Title>ww3 hs</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>raster_style</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#87CEEB" quantity="0.1"/>
              <sld:ColorMapEntry color="#4495D2" quantity="0.3"/>
              <sld:ColorMapEntry color="#005CB8" quantity="0.5"/>
              <sld:ColorMapEntry color="#007D77" quantity="0.75"/>
              <sld:ColorMapEntry color="#00CC00" quantity="1.25"/>
              <sld:ColorMapEntry color="#91FF00" quantity="1.75"/>
              <sld:ColorMapEntry color="#FFFF00" quantity="2.5"/>
              <sld:ColorMapEntry color="#FFD21F" quantity="3.25"/>
		       <sld:ColorMapEntry color="#FFA500" quantity="4"/>
		       <sld:ColorMapEntry color="#F57200" quantity="5"/>
              <sld:ColorMapEntry color="#FF0000" quantity="6"/>
              <sld:ColorMapEntry color="#C20101" quantity="7.5"/>
              <sld:ColorMapEntry color="#FD089F" quantity="9"/>
              <sld:ColorMapEntry color="#C72290" quantity="11"/>
              <sld:ColorMapEntry color="#B922C7" quantity="14"/>
              <sld:ColorMapEntry color="#611269" quantity="300"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
