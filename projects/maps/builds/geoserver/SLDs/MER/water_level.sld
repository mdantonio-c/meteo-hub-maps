<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0"
  xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd"
  xmlns="http://www.opengis.net/sld"
  xmlns:ogc="http://www.opengis.net/ogc"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>water_level</Name>
    <UserStyle>
      <Title>Water Level (m)</Title>
      <FeatureTypeStyle>
        <Rule>
          <RasterSymbolizer>
            <ChannelSelection>
              <GrayChannel>
                <SourceChannelName>1</SourceChannelName>
              </GrayChannel>
            </ChannelSelection>
            <ColorMap type="intervals">
              <ColorMapEntry color="#08306B" quantity="-0.70" label="-0.70 m" opacity="1.0"/>
              <ColorMapEntry color="#08519C" quantity="-0.60" label="-0.60 m" opacity="1.0"/>
              <ColorMapEntry color="#2171B5" quantity="-0.50" label="-0.50 m" opacity="1.0"/>
              <ColorMapEntry color="#4292C6" quantity="-0.40" label="-0.40 m" opacity="1.0"/>
              <ColorMapEntry color="#6BAED6" quantity="-0.30" label="-0.30 m" opacity="1.0"/>
              <ColorMapEntry color="#9ECAE1" quantity="-0.20" label="-0.20 m" opacity="1.0"/>
              <ColorMapEntry color="#C6DBEF" quantity="-0.10" label="-0.10 m" opacity="1.0"/>
              <ColorMapEntry color="#E5F5E0" quantity="0.00"  label="0.00 m"  opacity="1.0"/>
              <ColorMapEntry color="#C7E9C0" quantity="0.10"  label="0.10 m"  opacity="1.0"/>
              <ColorMapEntry color="#A1D99B" quantity="0.20"  label="0.20 m"  opacity="1.0"/>
              <ColorMapEntry color="#74C476" quantity="0.30"  label="0.30 m"  opacity="1.0"/>
              <ColorMapEntry color="#41AB5D" quantity="0.40"  label="0.40 m"  opacity="1.0"/>
              <ColorMapEntry color="#FFFFB2" quantity="0.50"  label="0.50 m"  opacity="1.0"/>
              <ColorMapEntry color="#FED976" quantity="0.60"  label="0.60 m"  opacity="1.0"/>
              <ColorMapEntry color="#FEB24C" quantity="0.70"  label="0.70 m"  opacity="1.0"/>
              <ColorMapEntry color="#FD8D3C" quantity="0.80"  label="0.80 m"  opacity="1.0"/>
              <ColorMapEntry color="#FC4E2A" quantity="0.90"  label="0.90 m"  opacity="1.0"/>
              <ColorMapEntry color="#E31A1C" quantity="1.00"  label="1.00 m"  opacity="1.0"/>
              <ColorMapEntry color="#C51B8A" quantity="1.10"  label="1.10 m"  opacity="1.0"/>
              <ColorMapEntry color="#9E017E" quantity="1.20"  label="1.20 m"  opacity="1.0"/>
              <ColorMapEntry color="#6A00A8" quantity="1.30"  label="1.30 m"  opacity="1.0"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
