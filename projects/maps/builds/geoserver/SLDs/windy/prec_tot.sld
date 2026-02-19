<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>prp_all</sld:Name>
    <sld:UserStyle>
      <sld:Name>prp_all</sld:Name>
      <sld:Title>Precipitation All Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#dbf4fb" opacity="0" quantity="0.0000001"/>
              <sld:ColorMapEntry color="#dbf4fb" quantity="0.5" label="1"/>
              <sld:ColorMapEntry color="#b6e8f6" quantity="1" label="2"/>
              <sld:ColorMapEntry color="#78dbf6" quantity="2" label="5"/>
              <sld:ColorMapEntry color="#19c2f0" quantity="5" label="10"/>
              <sld:ColorMapEntry color="#71a2d6" quantity="10" label="15"/>
              <sld:ColorMapEntry color="#518dcd" quantity="15" label="20"/>
              <sld:ColorMapEntry color="#1b4674" quantity="20" label="30"/>
              <sld:ColorMapEntry color="#0f2743" quantity="30" label="40"/>
              <sld:ColorMapEntry color="#f7ec31" quantity="40" label="50"/>
              <sld:ColorMapEntry color="#e86411" quantity="50" label="75"/>
              <sld:ColorMapEntry color="#e22208" quantity="75" label="100"/>
              <sld:ColorMapEntry color="#961405" quantity="100" label="150"/>
              <sld:ColorMapEntry color="#5b0c03" quantity="150" label="200"/>
              <sld:ColorMapEntry color="#a810a3" quantity="200" label="300"/>
              <sld:ColorMapEntry color="#f47fc0" quantity="300" label="500"/>
              <sld:ColorMapEntry color="#ebbfe9" quantity="500" label="750"/>
              <sld:ColorMapEntry color="#808060" quantity="750" label="1000"/>
              <sld:ColorMapEntry color="#3A3A2C" quantity="1000"/>
              <sld:ColorMapEntry color="#3A3A2C" quantity="10000"/>
            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
