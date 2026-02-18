<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor 
    xmlns:sld="http://www.opengis.net/sld" 
    xmlns="http://www.opengis.net/sld" 
    xmlns:gml="http://www.opengis.net/gml" 
    xmlns:ogc="http://www.opengis.net/ogc" 
    version="1.0.0">

  <sld:NamedLayer>
    <sld:Name>zero_degree_level</sld:Name>

    <sld:UserStyle>
      <sld:Name>zero_degree_level</sld:Name>
      <sld:Title>Zero degree level</sld:Title>

      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ColorMap type="intervals">

              <!-- -500 to 10 -->
              <sld:ColorMapEntry color="#efd9ff" quantity="10" label="10"/>

              <sld:ColorMapEntry color="#a47bf7" quantity="100" label="100"/>
              <sld:ColorMapEntry color="#7620cc" quantity="200" label="200"/>
              <sld:ColorMapEntry color="#4b0082" quantity="300" label="300"/>
              <sld:ColorMapEntry color="#3a0ca3" quantity="400" label="400"/>
              <sld:ColorMapEntry color="#1f4ed8" quantity="500" label="500"/>
              <sld:ColorMapEntry color="#1b9dce" quantity="600" label="600"/>
              <sld:ColorMapEntry color="#4cc9f0" quantity="800" label="800"/>
              <sld:ColorMapEntry color="#72efdd" quantity="1000" label="1000"/>
              <sld:ColorMapEntry color="#098400" quantity="1200" label="1200"/>
              <sld:ColorMapEntry color="#12d500" quantity="1400" label="1400"/>
              <sld:ColorMapEntry color="#c7f000" quantity="1600" label="1600"/>
              <sld:ColorMapEntry color="#fffc0a" quantity="1800" label="1800"/>
              <sld:ColorMapEntry color="#ffd803" quantity="2000" label="2000"/>
              <sld:ColorMapEntry color="#fb9f00" quantity="2500" label="2500"/>
              <sld:ColorMapEntry color="#e85d04" quantity="3000" label="3000"/>
              <sld:ColorMapEntry color="#ec1717" quantity="3500" label="3500"/>
              <sld:ColorMapEntry color="#b51717" quantity="4000" label="4000"/>
              <sld:ColorMapEntry color="#8e0000" quantity="4500" label="4500"/>
              <sld:ColorMapEntry color="#6a040f" quantity="5000" label="5000"/>
              <sld:ColorMapEntry color="#370617" quantity="10000"/>

            </sld:ColorMap>

            <sld:ContrastEnhancement/>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>

    </sld:UserStyle>
  </sld:NamedLayer>

</sld:StyledLayerDescriptor>
