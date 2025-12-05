<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>tp_quintile_1</Name>
    <UserStyle>
      <Title>Total Precipitation - Extreme Low (20th Percentile)</Title>
      <FeatureTypeStyle>
        <Rule>
          <RasterSymbolizer>
            <Opacity>1.0</Opacity>
            <ColorMap type="intervals">
              <ColorMapEntry color="#FFFFFF" quantity="35" opacity="0"/>
              <ColorMapEntry color="#e2d7cc" quantity="50"/>
              <ColorMapEntry color="#c5af99" quantity="65"/>
              <ColorMapEntry color="#a78766" quantity="80"/>
              <ColorMapEntry color="#8a5f33" quantity="90"/>
              <ColorMapEntry color="#6d3700" quantity="100"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
