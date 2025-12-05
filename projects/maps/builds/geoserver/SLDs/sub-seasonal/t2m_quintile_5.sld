<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>t2m_quintile_5</Name>
    <UserStyle>
      <Title>Temperature 2m - Extreme High (80th Percentile)</Title>
      <FeatureTypeStyle>
        <Rule>
          <RasterSymbolizer>
            <Opacity>1.0</Opacity>
            <ColorMap type="intervals">
              <ColorMapEntry color="#FFFFFF" quantity="33" opacity="0"/>
              <ColorMapEntry color="#e4cccc" quantity="50"/>
              <ColorMapEntry color="#c99999" quantity="65"/>
              <ColorMapEntry color="#ad6666" quantity="80"/>
              <ColorMapEntry color="#923333" quantity="90"/>
              <ColorMapEntry color="#770000" quantity="100"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
