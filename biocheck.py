import argparse
import binascii
import hashlib
import logging
import os
import pathlib
import sys
from datetime import datetime, timedelta

from lxml import etree


logger = logging.getLogger(__name__)


__copyright__ = 'Copyright (C) 2023 S[&]T, The Netherlands.'
__version__ = '1.0'

"""Perform consistency checks on BIOMASS products.

Check the contents of the BIOMASS products against information included in
the Main Product Header file, and also perform checks on the components
size and checksums.

All XML files included in the product are checked against their schema
(if available).

Additional checks on consistency between the product name and information
included in the MPH file are also performed.
"""

NSBIO = '{http://earth.esa.int/biomass/1.0}'
NSEOP = '{http://www.opengis.net/eop/2.1}'
NSOWS = '{http://www.opengis.net/ows/2.0}'
NSXLINK = '{http://www.w3.org/1999/xlink}'

# This is created with:
# xsltproc filter.xslt bio.xsd | xmllint --format -
# with filter.xslt being:
#   <xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
#                   xmlns:xsd="http://www.w3.org/2001/XMLSchema">
#     <xsl:output omit-xml-declaration="yes"/>
#     <xsl:strip-space elements="xsd:element" />
#     <xsl:template match="node()|@*"><xsl:copy><xsl:apply-templates select="node()|@*"/></xsl:copy></xsl:template>
#     <xsl:template match="xsd:annotation"/>
#   </xsl:stylesheet>
builtin_mph_schema = """<?xml version="1.0"?>
<schema xmlns="http://www.w3.org/2001/XMLSchema" xmlns:gml="http://www.opengis.net/gml/3.2"
        xmlns:ows="http://www.opengis.net/ows/2.0" xmlns:bio="http://earth.esa.int/biomass/1.0"
        xmlns:sar="http://www.opengis.net/sar/2.1" xmlns:eop="http://www.opengis.net/eop/2.1"
        attributeFormDefault="unqualified" elementFormDefault="qualified"
        targetNamespace="http://earth.esa.int/biomass/1.0" version="1.0">
  <import namespace="http://www.opengis.net/sar/2.1"
          schemaLocation="http://schemas.opengis.net/eompom/1.1/xsd/sar.xsd"/>
  <import namespace="http://www.opengis.net/gml/3.2" schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd"/>
  <import namespace="http://www.opengis.net/eop/2.1"
          schemaLocation="http://schemas.opengis.net/eompom/1.1/xsd/eop.xsd"/>
  <import namespace="http://www.opengis.net/ows/2.0" schemaLocation="http://schemas.opengis.net/ows/2.0/owsAll.xsd"/>
  <element name="EarthObservation" type="bio:EarthObservationType" substitutionGroup="sar:EarthObservation"/>
  <complexType name="EarthObservationType">
    <complexContent>
      <extension base="sar:EarthObservationType"/>
    </complexContent>
  </complexType>
  <complexType name="EarthObservationPropertyType">
    <sequence minOccurs="0">
      <element ref="bio:EarthObservation"/>
    </sequence>
    <attributeGroup ref="gml:AssociationAttributeGroup"/>
    <attributeGroup ref="gml:OwnershipAttributeGroup"/>
  </complexType>
  <element name="Acquisition" type="bio:AcquisitionType" substitutionGroup="sar:Acquisition"/>
  <complexType name="AcquisitionType">
    <complexContent>
      <extension base="sar:AcquisitionType">
        <sequence>
          <element name="missionPhase" type="bio:missionPhaseType" minOccurs="0"/>
          <element name="instrumentConfID" type="integer" minOccurs="0"/>
          <element name="dataTakeID" type="integer" minOccurs="0" maxOccurs="unbounded"/>
          <element name="orbitDriftFlag" type="boolean" minOccurs="0"/>
          <element name="globalCoverageID" type="bio:globalCoverageIDType" minOccurs="0"/>
          <element name="majorCycleID" type="bio:majorCycleIDType" minOccurs="0"/>
          <element name="repeatCycleID" type="bio:repeatCycleIDType" minOccurs="0"/>
          <element name="tileID" type="string" minOccurs="0" maxOccurs="unbounded"/>
          <element name="basinID" type="string" minOccurs="0" maxOccurs="unbounded"/>
        </sequence>
      </extension>
    </complexContent>
  </complexType>
  <complexType name="AcquisitionPropertyType">
    <sequence>
      <element ref="bio:Acquisition"/>
    </sequence>
    <attributeGroup ref="gml:OwnershipAttributeGroup"/>
  </complexType>
  <simpleType name="missionPhaseType">
    <restriction base="string">
      <enumeration value="COMMISSIONING"/>
      <enumeration value="INTERFEROMETRIC"/>
      <enumeration value="TOMOGRAPHIC"/>
    </restriction>
  </simpleType>
  <simpleType name="globalCoverageIDType">
    <restriction base="string">
      <enumeration value="1"/>
      <enumeration value="2"/>
      <enumeration value="3"/>
      <enumeration value="4"/>
      <enumeration value="5"/>
      <enumeration value="6"/>
      <enumeration value="NA"/>
    </restriction>
  </simpleType>
  <simpleType name="majorCycleIDType">
    <restriction base="string">
      <enumeration value="1"/>
      <enumeration value="2"/>
      <enumeration value="3"/>
      <enumeration value="4"/>
      <enumeration value="5"/>
      <enumeration value="6"/>
      <enumeration value="7"/>
      <enumeration value="NA"/>
    </restriction>
  </simpleType>
  <simpleType name="repeatCycleIDType">
    <restriction base="string">
      <enumeration value="1"/>
      <enumeration value="2"/>
      <enumeration value="3"/>
      <enumeration value="4"/>
      <enumeration value="5"/>
      <enumeration value="6"/>
      <enumeration value="7"/>
      <enumeration value="8"/>
      <enumeration value="DR"/>
      <enumeration value="NA"/>
    </restriction>
  </simpleType>
  <element name="ProductInformation" type="bio:ProductInformationType" substitutionGroup="eop:ProductInformation"/>
  <complexType name="ProductInformationType">
    <complexContent>
      <extension base="eop:ProductInformationType">
        <sequence>
          <element name="rds" type="string" minOccurs="0"/>
        </sequence>
      </extension>
    </complexContent>
  </complexType>
  <complexType name="ProductInformationPropertyType">
    <complexContent>
      <extension base="eop:ProductInformationPropertyType">
        <sequence>
          <element ref="bio:ProductInformation"/>
        </sequence>
      </extension>
    </complexContent>
  </complexType>
  <element name="EarthObservationMetaData" type="bio:EarthObservationMetaDataType"
           substitutionGroup="eop:EarthObservationMetaData"/>
  <complexType name="EarthObservationMetaDataType">
    <complexContent>
      <extension base="eop:EarthObservationMetaDataType">
        <sequence>
          <element name="TAI-UTC" type="integer" minOccurs="0"/>
          <element name="numOfTFs" type="integer" minOccurs="0"/>
          <element name="numOfTFsWithErrors" type="integer" minOccurs="0"/>
          <element name="numOfCorruptedTFs" type="integer" minOccurs="0"/>
          <element name="numOfISPs" type="integer" minOccurs="0"/>
          <element name="numOfISPsWithErrors" type="integer" minOccurs="0"/>
          <element name="numOfCorruptedISPs" type="integer" minOccurs="0"/>
          <element name="numOfLines" type="string" minOccurs="0"/>
          <element name="numOfMissingLines" type="string" minOccurs="0"/>
          <element name="numOfCorruptedLines" type="string" minOccurs="0"/>
          <element name="isIncomplete" type="boolean" minOccurs="0"/>
          <element name="isPartial" type="boolean" minOccurs="0"/>
          <element name="isMerged" type="boolean" minOccurs="0"/>
          <element name="refDoc" type="string" minOccurs="0" maxOccurs="unbounded"/>
        </sequence>
      </extension>
    </complexContent>
  </complexType>
  <complexType name="EarthObservationMetaDataPropertyType">
    <sequence>
      <element ref="bio:EarthObservationMetaData"/>
    </sequence>
    <attributeGroup ref="gml:OwnershipAttributeGroup"/>
  </complexType>
  <element name="ProcessingInformation" type="bio:ProcessingInformationType"
           substitutionGroup="eop:ProcessingInformation"/>
  <complexType name="ProcessingInformationType">
    <complexContent>
      <extension base="eop:ProcessingInformationType">
        <sequence>
          <element name="sourceProduct" type="string" minOccurs="0" maxOccurs="unbounded"/>
        </sequence>
      </extension>
    </complexContent>
  </complexType>
  <complexType name="ProcessingInformationPropertyType">
    <complexContent>
      <extension base="eop:ProcessingInformationPropertyType">
        <sequence>
          <element ref="bio:ProcessingInformation"/>
        </sequence>
      </extension>
    </complexContent>
  </complexType>
</schema>
"""


def base36encode(number):
    """Converts an integer to a base36 string."""
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if not isinstance(number, int):
        raise TypeError('number must be an integer')
    base36 = ''
    sign = ''
    if number < 0:
        sign = '-'
        number = -number
    if 0 <= number < len(alphabet):
        return sign + alphabet[number]
    while number != 0:
        number, i = divmod(number, len(alphabet))
        base36 = alphabet[i] + base36
    return sign + base36


def check_file_against_schema(xmlfile, schema):
    if isinstance(schema, str) and schema.startswith('<?xml'):
        xmlschema = etree.XMLSchema(etree.fromstring(schema))
        schema = "built-in schema"
    else:
        try:
            etree.clear_error_log()
            xmlschema = etree.XMLSchema(etree.parse(os.fspath(schema)).getroot())
        except etree.Error as exc:
            logger.error(f"could not parse schema '{schema}'")
            for error in exc.error_log:
                logger.error(f"{error.filename}:{error.line}: {error.message}")
            return False
    try:
        etree.clear_error_log()
        xmlschema.assertValid(etree.parse(os.fspath(xmlfile)))
    except etree.DocumentInvalid as exc:
        logger.error(f"could not verify '{xmlfile}' against schema '{schema}'")
        for error in exc.error_log:
            logger.error(f"{error.filename}:{error.line}: {error.message}")
        return False
    logger.debug(f"file '{xmlfile}' valid according to schema '{schema}'")
    return True


def is_xml(filename):
    filename = pathlib.Path(filename)
    return filename.suffix.lower() == '.xml' and filename.name[0] != "."


def verify_biomass_product(product, use_mph_schema=False):
    has_errors = False
    has_warnings = False

    product = pathlib.Path(product)

    if not product.exists():
        logger.error(f"could not find '{product}'")
        return 2

    mphfile = product / (product.name.lower() + '.xml')
    if not mphfile.exists():
        logger.error(f"could not find '{mphfile}'")
        return 2

    if use_mph_schema:
        if not check_file_against_schema(mphfile, builtin_mph_schema):
            has_errors = True
    try:
        etree.clear_error_log()
        mph = etree.parse(os.fspath(mphfile))
    except etree.Error as exc:
        logger.error(f"could not parse xml file '{mphfile}'")
        for error in exc.error_log:
            logger.error(f"{error.filename}:{error.line}: {error.message}")
        return 2

    # check encoded creation date in product name
    epoch = datetime(2000, 1, 1)
    mph_date = mph.find(f'.//{NSEOP}processingDate').text
    try:
        compact_mph_date = base36encode(int((datetime.strptime(mph_date, '%Y-%m-%dT%H:%M:%SZ') - epoch).total_seconds()))
    except ValueError as exc:
        logger.error(f"invalid value for processingDate in '{mphfile}' ({str(exc)})")
        has_errors = True
    else:
        compact_creation_date = product.name[-6:]
        creation_date = (epoch + timedelta(seconds=int(compact_creation_date, 36))).strftime('%Y-%m-%dT%H:%M:%SZ')
        if compact_creation_date != compact_mph_date:
            logger.error(f"compact creation date in '{product}' ({creation_date}|{compact_creation_date}) does not "
                         f"match processing date from MPH ({mph_date}|{compact_mph_date})")
            has_errors = True

    # find list of files in product
    files = [item for item in product.rglob("*") if item.is_file()]
    files.remove(mphfile)

    # check files that are referenced in manifest file
    for product_info in mph.findall(f'.//{NSBIO}ProductInformation'):
        href = product_info.find(f'{NSEOP}fileName/{NSOWS}ServiceReference').get(f'{NSXLINK}href')
        if href == product.name:
            continue
        filepath = product / href
        if filepath in files:
            files.remove(filepath)
        else:
            logger.error(f"MPH reference '{href}' does not exist in product '{product}'")
            has_errors = True
            continue
        # check file size
        size_element = product_info.find(f'{NSEOP}size')
        if size_element is not None:
            filesize = filepath.stat().st_size
            if filesize != int(size_element.text):
                logger.error(f"file size for '{href}' ({filesize}) does not match file size in MPH "
                             f"({size_element.text}) for product '{product}'")
                has_errors = True
        # check withl XML Schema (if there is one)
        rds = product_info.find(f'{NSBIO}rds')
        if rds is not None:
            schemafile = product / rds.text
            if schemafile in files:
                files.remove(schemafile)
                if not check_file_against_schema(filepath, schemafile):
                    has_errors = True
            else:
                logging.error(f"schema file '{schemafile}' does not exist")
                has_errors = True

    # report on files in the BIOMASS product that are not referenced by the MPH
    for file in files:
        logging.warning(f"file '{file.relative_to(product)}' found in product '{product}' but not included in MPH")
        has_warnings = True

    if has_errors:
        return 2
    if has_warnings:
        return 3
    return 0


def main():
    logging.basicConfig(format='%(levelname)s: %(message)s', stream=sys.stdout)
    logging.captureWarnings(True)

    # This parser is used in combination with the parse_known_args() function as a way to implement a "--version"
    # option that prints version information and exits, and is included in the help message.
    #
    # The "--version" option should have the same semantics as the "--help" option in that if it is present on the
    # command line, the corresponding action should be invoked directly, without checking any other arguments.
    # However, the argparse module does not support user defined options with such semantics.
    version_parser = argparse.ArgumentParser(add_help=False)
    version_parser.add_argument('--version', action='store_true', help='output version information and exit')

    parser = argparse.ArgumentParser(prog='biocheck', description=__doc__, parents=[version_parser])
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='suppress standard output messages and warnings, only errors are printed to screen')
    parser.add_argument('-s', '--schema', action='store_true',
                        help='verify Main Product Header against schema (requires internet access)')
    parser.add_argument('products', nargs='+', metavar='<BIOMASS product>')

    args, unused_args = version_parser.parse_known_args()
    if args.version:
        print(f'biocheck v{__version__}')
        print(__copyright__)
        print()
        sys.exit(0)

    args = parser.parse_args(unused_args)

    logging.getLogger().setLevel('ERROR' if args.quiet else 'INFO')
    try:
        return_code = 0
        for arg in args.products:
            if not args.quiet:
                print(arg)
            result = verify_biomass_product(arg, args.schema)
            if result != 0:
                if result < return_code or return_code == 0:
                    return_code = result
            if not args.quiet:
                print('')
        sys.exit(return_code)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == '__main__':
    main()
