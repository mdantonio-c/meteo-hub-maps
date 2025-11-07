<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld"
                           xmlns="http://www.opengis.net/sld"
                           xmlns:gml="http://www.opengis.net/gml"
                           xmlns:ogc="http://www.opengis.net/ogc"
                           version="1.0.0">
  <sld:NamedLayer>
    <sld:Name>temp_anomaly</sld:Name>
    <sld:UserStyle>
      <sld:Name>temp_anomaly</sld:Name>
      <sld:Title>Temperature Anomaly Color Map</sld:Title>
      <sld:FeatureTypeStyle>
        <sld:Name>name</sld:Name>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">

              <sld:ColorMapEntry color="#c667e0" quantity="-10"/>
              <sld:ColorMapEntry color="#9b41b4" quantity="-3"/>
              <sld:ColorMapEntry color="#541a8a" quantity="-2.8"/>
              <sld:ColorMapEntry color="#231a8a" quantity="-2.6"/>
              <sld:ColorMapEntry color="#002c61" quantity="-2.4"/>
              <sld:ColorMapEntry color="#003e8a" quantity="-2.2"/>
              <sld:ColorMapEntry color="#0955b3" quantity="-2"/>
              <sld:ColorMapEntry color="#005485" quantity="-1.8"/>
              <sld:ColorMapEntry color="#006fb0" quantity="-1.6"/>
              <sld:ColorMapEntry color="#0089d9" quantity="-1.4"/>
              <sld:ColorMapEntry color="#00a2ff" quantity="-1.2"/>
              <sld:ColorMapEntry color="#3bb7ff" quantity="-1"/>
              <sld:ColorMapEntry color="#6bc9ff" quantity="-0.8"/>
              <sld:ColorMapEntry color="#99daff" quantity="-0.6"/>
              <sld:ColorMapEntry color="#b5e4ff" quantity="-0.4"/>
              <sld:ColorMapEntry color="#ffffff" quantity="-0.2"/>

              <sld:ColorMapEntry color="#ffffff" quantity="0.2"/>
              <sld:ColorMapEntry color="#ffe3e3" quantity="0.4"/>
              <sld:ColorMapEntry color="#ffc4c4" quantity="0.6"/>
              <sld:ColorMapEntry color="#ffa6a6" quantity="0.8"/>
              <sld:ColorMapEntry color="#ff7d7d" quantity="1"/>
              <sld:ColorMapEntry color="#fe5b5b" quantity="1.2"/>
              <sld:ColorMapEntry color="#ff2929" quantity="1.4"/>
              <sld:ColorMapEntry color="#ff0505" quantity="1.6"/>
              <sld:ColorMapEntry color="#e00404" quantity="1.8"/>
              <sld:ColorMapEntry color="#c90000" quantity="2"/>
              <sld:ColorMapEntry color="#a60000" quantity="2.2"/>
              <sld:ColorMapEntry color="#7a0000" quantity="2.4"/>
              <sld:ColorMapEntry color="#520000" quantity="2.6"/>
              <sld:ColorMapEntry color="#330000" quantity="2.8"/>
              <sld:ColorMapEntry color="#240000" quantity="3"/>
              <sld:ColorMapEntry color="#0f0000" quantity="10"/>

            </sld:ColorMap>
            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </sld:NamedLayer>
</sld:StyledLayerDescriptor>
