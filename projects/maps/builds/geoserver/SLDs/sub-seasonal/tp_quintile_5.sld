<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>tp_quintile_5</Name>
    <UserStyle>
      <Title>Total Precipitation - Extreme High (80th Percentile)</Title>
      <FeatureTypeStyle>
        <Rule>
          <RasterSymbolizer>
            <Opacity>1.0</Opacity>
            <ColorMap type="intervals">
              <ColorMapEntry color="#FFFFFF" quantity="35" opacity="0"/>
              <ColorMapEntry color="#cfd9d2" quantity="50"/>
              <ColorMapEntry color="#9fb3a6" quantity="65"/>
              <ColorMapEntry color="#6f8c79" quantity="80"/>
              <ColorMapEntry color="#3f664c" quantity="90"/>
              <ColorMapEntry color="#0f401f" quantity="100"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
