<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>t2m_terzile_1</Name>
    <UserStyle>
      <Title>Temperature 2m - Below Average</Title>
      <FeatureTypeStyle>
        <Rule>
          <RasterSymbolizer>
            <Opacity>1.0</Opacity>
            <ColorMap type="intervals">
              <ColorMapEntry color="#FFFFFF" quantity="33" opacity="0"/>
              <ColorMapEntry color="#cce5ff" quantity="50"/>
              <ColorMapEntry color="#99ccff" quantity="65"/>
              <ColorMapEntry color="#57abff" quantity="80"/>
              <ColorMapEntry color="#0b70d6" quantity="90"/>
              <ColorMapEntry color="#004487" quantity="101"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
