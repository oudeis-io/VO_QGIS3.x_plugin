# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GAVOCoveage
                                 A QGIS plugin
 Get coveage from  access_url
                              -------------------
        begin                : 2018-02-08
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Mikhail Minin
        email                : m.minin@jacobs-university.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from __future__ import print_function
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import object
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
# Initialize Qt resources from file resources.py
from . import resources
# Import the code for the dialog
from .gavo_coverage_dialog import GAVOCoverageDialog
import os.path
from osgeo import osr, gdal, gdalconst # needed for projecting the raster cube
#import os.path
import threading, time
from qgis.core import *
from astropy.table import Table
import shapefile
import numpy as np
import os
import tempfile
import geojson
import qgis
import urllib.request, urllib.parse, urllib.error
#import iface

def LoadRasterFromSelectedFeature(miface):
    iface=miface
    def getSelFeat(): ### Get feature
       layer = qgis.utils.iface.activeLayer()
       selected_features = layer.selectedFeatures()
       if len(selected_features) == 1:
          return selected_features[0]
       else:
          # fix_print_with_import
          print("Please select only one feature")
#
    mf=getSelFeat()
    CovURL=mf.attribute('access_url')
    CovProj=mf.attribute('spatial_coordinate_description')
#
    LonMin=float(mf.attribute('c1min'))
    LonMax=float(mf.attribute('c1max'))
    LatMin=float(mf.attribute('c2min'))
    LatMax=float(mf.attribute('c2max'))
### This will only work with CRISM dataset, since params e and n are ad-hoc
##  Ideally this data should be gathered from the image that was downloaded
    ImgWidth = float(mf.attribute('image_width')) 
    ImgHeight= float(mf.attribute('image_height')) 
# Make temporary directory
    destinationPath = tempfile.mkdtemp()
    destinationFileName =  mf.attribute('granule_uid') + ".tif" ## <= ASSUMING TIFF FILE! TODO: Use mimetype from access_format!
    destinationTarget = '/'.join([destinationPath, destinationFileName])
#
    urllib.request.urlretrieve (CovURL,destinationTarget)
########### Apply a map => Cancel that! We'll assign proj4 string instead later!
#    with open(destinationTarget+'w', 'w') as w:
#        ww=lambda n: w.write(str(n)+'\n')
#        sizeX = (LonMax-LonMin)/ImgWidth
#        sizeY = -(LatMax-LatMin)/ImgHeight
#        origX= LonMin
#        origY= LatMax
#        map(ww, [sizeX,0,0,sizeY,origX,origY])
# Redefine raster CRS (update to the one supplied by DaCHS):
    dataset = gdal.Open(destinationTarget, GA_Update) #1=GA_Update
    srs = osr.SpatialReference()
    srs.ImportFromProj4(str(CovProj))
    dataset.SetProjection( srs.ExportToWkt() )
    q=dataset.GetRasterBand(1)#
    q.SetNoDataValue(65535)#
    q=None#
    dataset=None
# Add layer to the map:
    coverageRasterCubeLayer=iface.addRasterLayer(destinationTarget, destinationFileName)
    QgsMessageLog.logMessage('creating crs from proj4')
    myCRS=QgsCoordinateReferenceSystem()
    myCRS.createFromProj4(CovProj)
    QgsMessageLog.logMessage('setting layer crs')
    coverageRasterCubeLayer.setCrs(myCRS)
    cRBC=coverageRasterCubeLayer.bandCount()
    QgsMessageLog.logMessage('coverage contains ' + str(cRBC) + ' bands')
#    QgsMessageLog.logMessage('Assuming NODATA = 65535')
    coverageLayerDataProvider=coverageRasterCubeLayer.dataProvider()
#    coverageLayerDataProvider.setNoDataValue(1,65535)
#    for i in range(1, cRBC + 1): coverageLayerDataProvider.setNoDataValue(i,65535)
    coverageRenderer=QgsMultiBandColorRenderer(coverageLayerDataProvider,int(0.5+cRBC/6),int(0.5+cRBC/2),int(0.5+5*cRBC/6))
    QgsMessageLog.logMessage('setting up contrast enhancement')
    def getContrastEnhancer():
        ce =QgsContrastEnhancement(coverageLayerDataProvider.dataType(0))
        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
        ce.setMinimumValue(0) # ASSUMING TIFF DATA RANGES FROM 0 TO 1 ! TODO: Get min/max values from statistics!
        ce.setMaximumValue(1)
        return ce
    coverageRenderer.setRedContrastEnhancement(getContrastEnhancer())
    coverageRenderer.setGreenContrastEnhancement(getContrastEnhancer())
    coverageRenderer.setBlueContrastEnhancement(getContrastEnhancer())
    coverageRasterCubeLayer.setRenderer(coverageRenderer)
    coverageRasterCubeLayer.triggerRepaint()


class GAVOCoverage(object):
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'GAVOCoverage_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)


        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&GAVO Coveage')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'GAVOCoverage')
        self.toolbar.setObjectName(u'GAVOCoverage')

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('GAVOCoverage', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        # Create the dialog (after translation) and keep reference
        self.dlg = GAVOCoverageDialog()

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/GAVOCoverage/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'GAVO Coveage'),
            callback=self.run,
            parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&GAVO Coverage'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar


    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            LoadRasterFromSelectedFeature(self.iface)
#pass
