<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>tp_terzile_3</Name>
    <UserStyle>
      <Title>Total Precipitation - Above Average</Title>
      <FeatureTypeStyle>
        <Rule>
          <RasterSymbolizer>
            <Opacity>1.0</Opacity>
            <ColorMap type="intervals">
              <ColorMapEntry color="#FFFFFF" quantity="35" opacity="0"/>
              <ColorMapEntry color="#d9f2d9" quantity="50"/>
              <ColorMapEntry color="#a6d8a8" quantity="65"/>
              <ColorMapEntry color="#73bf78" quantity="80"/>
              <ColorMapEntry color="#288a32" quantity="90"/>
              <ColorMapEntry color="#1f5c33" quantity="100"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
