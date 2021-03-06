from collections import defaultdict
import os

import numpy as np
import pandas as pd

from dsgrid import DSGridError, DSGridNotImplemented
from dsgrid.dataformat.datatable import Datatable
from dsgrid.dataformat.enumeration import (
    SectorEnumeration, GeographyEnumeration, EndUseEnumeration, 
    EndUseEnumerationBase, FuelEnumeration, MultiFuelEndUseEnumeration, 
    SingleFuelEndUseEnumeration, TimeEnumeration,
    allenduses,allsectors,annual,census_divisions,census_regions,conus,
    conus_counties,conus_states,counties,daily2012,daytypes,enduses,
    enumdata_folder,fuel_types,hourly2012,loss_state_groups,seasons,sectors,
    sectors_subsectors,states,weekdays,weekly2012)


class DimensionMap(object):
    def __init__(self,from_enum,to_enum):
        self.from_enum = from_enum
        self.to_enum = to_enum

    def map(self,from_id):
        """
        Returns the appropriate to_id.
        """
        return None

    def scale_factor(self,from_id):
        return 1.0

    def __repr__(self):
        return f"{self.__class__.__name__}({self.from_enum}, {self.to_enum})"


class TautologyMapping(DimensionMap):
    def __init__(self,from_to_enum):
        super().__init__(from_to_enum,from_to_enum)

    def map(self,from_id):
        return from_id


class FullAggregationMap(DimensionMap):

    def __init__(self,from_enum,to_enum,exclude_list=[]):
        """
        Parameters
        ----------
        from_enum : dsgrid.dataformat.enumeration.Enumeration
        to_enum : dsgrid.dataformat.enumeration.Enumeration
            Class must correspond to the same dimension as from_enum, and 
            the enumeration must have exactly one element
        exclude_list : list of from_enum.ids
            from_enum values that should be dropped from the aggregation
        """
        super().__init__(from_enum,to_enum)
        if len(to_enum.ids) > 1:
            raise DSGridError("FullAggregationMaps are aggregates that may exclude " + 
                "some items, but otherwise aggretate up to one quantity. " + 
                "to_enum {} contains too many items.".format(repr(to_enum)))
        self.to_id = to_enum.ids[0]

        self.exclude_list = exclude_list
        for exclude_item in self.exclude_list:
            if exclude_item not in from_enum.ids:
                raise DSGridError("exclude_list must contain ids in from_enum " + 
                    "that are to be exluded from the overall aggregation. "
                    "Found {} in exclude list, which is not in {}.".format(exclude_item,from_enum))

    def map(self,from_id):
        if from_id in self.exclude_list:
            return None
        return self.to_id


class FilterToSubsetMap(DimensionMap):
    def __init__(self,from_enum,to_enum):
        """
        Arguments:
            - to_enum (Enumeration) - should be a subset of from_enum
        """
        super().__init__(from_enum,to_enum)
        for to_id in to_enum.ids:
            if not to_id in from_enum.ids:
                raise DSGridError("to_enum should be a subset of from_enum")

    def map(self,from_id):
        if from_id in self.to_enum.ids:
            return from_id
        return None


class FilterToSingleFuelMap(DimensionMap):
    def __init__(self,from_enum,fuel_to_keep):
        assert isinstance(from_enum,MultiFuelEndUseEnumeration), "This map only applies to MultiFuelEndUseEnumerations"
        assert fuel_to_keep in from_enum.fuel_enum.ids, "{} is not a fuel_id in {}".format(fuel_to_keep,from_enum.fuel_enum)
        to_enum_name = from_enum.name + " ({})".format(from_enum.fuel_enum.get_name(fuel_to_keep))
        ids = []; names = []; self._map = {}
        for i, id in enumerate(from_enum.ids):
            if id[1] == fuel_to_keep:
                ids.append(id[0]); names.append(from_enum._names[i])
                self._map[id] = id[0]
            else:
                self._map[id] = None
        to_enum = SingleFuelEndUseEnumeration(to_enum_name,
                                              ids,names,
                                              fuel=from_enum.fuel_enum.get_name(fuel_to_keep),
                                              units=from_enum.fuel_enum.get_units(fuel_to_keep))
        super().__init__(from_enum,to_enum)

    def map(self,from_id):
        return self._map[from_id]


class ExplicitMap(DimensionMap):
    def __init__(self,from_enum,to_enum,dictmap):
        super().__init__(from_enum,to_enum)
        self._dictmap = defaultdict(lambda: None)

    def map(self,from_id):
        return self._dictmap[from_id]

    @classmethod
    def create_from_csv(cls,from_enum,to_enum,filepath):
        mapdata = pd.read_csv(filepath,dtype=str)
        return cls(from_enum,to_enum,cls._make_dictmap(mapdata))

    @classmethod
    def _make_dictmap(cls,mapdata): pass


class ExplicitDisaggregation(ExplicitMap):
    def __init__(self,from_enum,to_enum,dictmap,scaling_datafile=None):
        """
        If no scaling_datafile, scaling factors are assumed to be 1.0.
        """
        super().__init__(from_enum,to_enum,dictmap)
        self._dictmap = defaultdict(lambda: [])
        for from_id, to_ids in dictmap.items():
            if from_id not in self.from_enum.ids:
                raise DSGridError("Id {} is not in from_enum {}.".format(from_id,self.from_enum))
            for to_id in to_ids:
                if to_id not in self.to_enum.ids:
                    raise DSGridError("Id {} is not in to_enum {}.".format(to_id,self.to_enum))
            self._dictmap[from_id] = to_ids
        # scaling_datafile must have to_enum as one of its dimensions
        if (scaling_datafile is not None) and (not scaling_datafile.contains(to_enum)):
            raise DSGridError("Datafile {} cannot be used to scale this map ".format(repr(scaling_datafile)) + 
                "because it does not contain to_enum {}.".format(repr(to_enum)))
        self._scaling_datafile = scaling_datafile
        self._scaling_datatable = None

    @property
    def default_scaling(self):
        return self._scaling_datafile is None

    @property
    def scaling_datatable(self):
        assert not self.default_scaling
        if self._scaling_datatable is None:
            self._scaling_datatable = Datatable(self._scaling_datafile)
        return self._scaling_datatable

    def get_scalings(self,to_ids):
        """
        Return an array of scalings for to_ids.
        """
        if self.default_scaling:
            return np.array([1.0 for to_id in to_ids]) 

        if isinstance(self.to_enum,SectorEnumeration):
            temp = self.scaling_datatable[to_ids,:,:,:]
            temp = temp.groupby(level='sector').sum()
        elif isinstance(self.to_enum,GeographyEnumeration):
            temp = self.scaling_datatable[:,to_ids,:,:]
            temp = temp.groupby(level='geography').sum()
        elif isinstance(self.to_enum,EndUseEnumerationBase):
            temp = self.scaling_datatable[:,:,to_ids,:]
            temp = temp.groupby(level='enduse').sum()
        else:
            assert isinstance(self.to_enum,TimeEnumeration)
            temp = self.scaling_datatable[:,:,:,to_ids]
            temp = temp.groupby(level='time').sum()

        # fraction of from_id that should go to each to_id
        temp = temp / temp.sum()
        result = np.array([temp[to_id] for to_id in to_ids])
        return result

    @classmethod
    def create_from_csv(cls,from_enum,to_enum,filepath,scaling_datafile=None):
        mapdata = pd.read_csv(filepath,dtype=str)
        return cls(from_enum,to_enum,cls._make_dictmap(mapdata),scaling_datafile=scaling_datafile)

    @classmethod
    def _make_dictmap(cls,mapdata):
        result = defaultdict(lambda: [])
        for from_id, to_id in zip(mapdata.from_id,mapdata.to_id):
            result[from_id].append(to_id)
        return result


class ExplicitAggregation(ExplicitMap):
    def __init__(self,from_enum,to_enum,dictmap):
        super().__init__(from_enum,to_enum,dictmap)
        for from_id, to_id in dictmap.items():
            if from_id not in self.from_enum.ids:
                raise DSGridError("Id {} is not in from_enum {}.".format(from_id,self.from_enum))
            if to_id not in self.to_enum.ids:
                raise DSGridError("Id {} is not in to_enum {}.".format(to_id,self.to_enum))
            self._dictmap[from_id] = to_id

    @classmethod
    def _make_dictmap(cls,mapdata):
        result = {}
        from_fuel_enduse = ('from_fuel_id' in mapdata.columns)
        to_fuel_enduse = ('to_fuel_id' in mapdata.columns)
        for row in mapdata.itertuples(index=False):
            from_key = (row.from_id, row.from_fuel_id) if from_fuel_enduse else row.from_id
            to_key = (row.to_id, row.to_fuel_id) if to_fuel_enduse else row.to_id
            result[from_key] = to_key
        return result


class UnitConversionMap(DimensionMap):
    CONVERSION_FACTORS = {
        ('kWh','MWh'): 1.0E-3,
        ('MWh','GWh'): 1.0E-3,
        ('GWh','TWh'): 1.0E-3
    }

    def __init__(self,from_enum,from_units,to_units):
        """
        Convert from_units to to_units.

        Parameters
        ----------
        from_enum : EndUseEnumerationBase
        from_units : list of str
            List of units in from_enum that are to be converted
        to_units : list of str
            List of units to convert to. Same length list as from_units.
        """
        assert isinstance(from_enum,EndUseEnumerationBase), "Unit conversion applies to EndUseEnumerations"
        assert not isinstance(from_enum,EndUseEnumeration), "Old-style end-use enumerations do not include units information"
        assert len(from_units) == len(to_units), "Cannot convert {} to {} since they are of a different number".format(from_units,to_units)
        assert len(from_units) > 0, "from_units is empty. Nothing to do."

        self._scale_map = defaultdict(lambda: 1.0)
        if isinstance(from_enum,SingleFuelEndUseEnumeration):
            assert len(from_units) == 1
            assert from_units[0] == from_enum._units
            to_enum_name = from_enum.name.replace(from_units[0],to_units[0])
            to_enum_name = to_enum_name.replace(from_units[0].lower(),to_units[0].lower())
            to_enum = SingleFuelEndUseEnumeration(to_enum_name,
                                                  from_enum.ids,
                                                  from_enum.names,
                                                  fuel=from_enum._fuel,
                                                  units=to_units[0])
            self._scale_map = self.scaling_factor(from_units[0],to_units[0])

        else:
            assert isinstance(from_enum,MultiFuelEndUseEnumeration)
            for from_unit in from_units:
                assert from_unit in from_enum.fuel_enum.units, "{} is not a unit in {!r}".format(from_unit,from_enum.fuel_enum)
            
            to_fuel_enum_units = []
            for unit in from_enum.fuel_enum.units:
                if unit in from_units:
                    to_fuel_enum_units.append(to_units[from_units.index(unit)])
                else:
                    to_fuel_enum_units.append(unit)
            
            to_fuel_enum = FuelEnumeration(from_enum.fuel_enum.name,
                                           from_enum.fuel_enum.ids,
                                           from_enum.fuel_enum.names,
                                           to_fuel_enum_units)
            
            to_enum = MultiFuelEndUseEnumeration(from_enum.name,
                                                 from_enum._ids,
                                                 from_enum._names,
                                                 to_fuel_enum,
                                                 from_enum._fuel_ids)
            for id in from_enum.ids:
                u = from_enum.units(id)
                if u in from_units:
                    self._scale_map[id] = self.scaling_factor(u,to_units[from_units.index(u)])

        super().__init__(from_enum,to_enum)

    def map(self,from_id):
        # no change in enduse or fuel id
        return from_id

    def scale_factor(self,from_id):
        if isinstance(self._scale_map,dict):
            return self._scale_map[from_id]
        return self._scale_map        

    @classmethod
    def scaling_factor(cls,from_unit,to_unit):
        key = (from_unit,to_unit)
        these_factors = cls._get_all_factors(to_unit, cls.CONVERSION_FACTORS)
        if key in these_factors:
            return these_factors[key]

        something_added = True
        while something_added:
            something_added = False
            to_expand = [(a_key, val) for a_key, val in these_factors.items()]
            for a_key, factor in to_expand:
                candidates = cls._get_all_factors(a_key[0], cls.CONVERSION_FACTORS, multiplier=factor)
                for b_key, val in candidates.items():
                    c_key = (b_key[0], to_unit)
                    if c_key not in these_factors:
                        these_factors[c_key] = val
                        something_added = True
            if key in these_factors:
                return these_factors[key]

        raise DSGridNotImplemented("No conversion factor available to go from {} to {}.".format(from_unit,to_unit))

    @classmethod
    def _get_all_factors(cls, to_unit, factors, multiplier = None):
        result = {}

        for units, factor in factors.items():
            from_u, to_u = units
            # directly in factors?
            if to_u == to_unit:
                result[units] = factor
        
            # in factors backward?
            if from_u == to_unit:
                result[(to_u, from_u)] = 1.0 / factor

        if multiplier is not None:
            for key in result:
                result[key] *= multiplier
        
        return result


class Mappings(object):

    def __init__(self):
        self._mappings = defaultdict(lambda: None)

    def add_mapping(self,mapping):
        self._mappings[(mapping.from_enum.name,mapping.to_enum.name)] = mapping

    def get_mapping(self,datafile,to_enum):
        
        from_enum = None
        if isinstance(to_enum,SectorEnumeration):
            from_enum = datafile.sector_enum
        elif isinstance(to_enum,GeographyEnumeration):
            from_enum = datafile.geo_enum
        elif isinstance(to_enum,EndUseEnumerationBase):
            from_enum = datafile.enduse_enum
        elif isinstance(to_enum,TimeEnumeration):
            from_enum = datafile.time_enum
        else:
            raise DSGridError("to_enum {} is not a recognized enumeration type.".format(repr(to_enum)))

        key = (from_enum.name,to_enum.name)
        if key in self._mappings:
            return self._mappings[key]

        # No immediate match
        # Is the requested mapping a tautology?
        if from_enum == to_enum:
            return TautologyMapping(to_enum)
        if from_enum.is_subset(to_enum):
            return TautologyMapping(to_enum)
        # Are elements in from_enum a subset of a stored mapping.from_enum?
        candidates = [mapping for key, mapping in self._mappings.items() if key[1] == to_enum.name]
        for candidate in candidates:
            okay = True
            for from_id in from_enum.ids:
                if from_id not in candidate.from_enum.ids:
                    okay = False
                    break
            if okay:
                return candidate
        return None

mappings = Mappings()

# key geography
mappings.add_mapping(ExplicitAggregation.create_from_csv(counties,states,os.path.join(enumdata_folder,'counties_to_states.csv')))
conus_states_list = pd.read_csv(os.path.join(enumdata_folder,'conus_to_states.csv'),dtype=str)['to_id'].tolist()
mappings.add_mapping(FullAggregationMap(states,conus,exclude_list=[state_id for state_id in states.ids if state_id not in conus_states_list]))
# full aggregations
mappings.add_mapping(FullAggregationMap(census_regions,conus))
mappings.add_mapping(FullAggregationMap(hourly2012,annual))
mappings.add_mapping(FullAggregationMap(daily2012,annual))
mappings.add_mapping(FullAggregationMap(weekly2012,annual))
mappings.add_mapping(FullAggregationMap(seasons,annual))
mappings.add_mapping(FullAggregationMap(sectors,allsectors))
mappings.add_mapping(FullAggregationMap(sectors_subsectors,allsectors))
mappings.add_mapping(FullAggregationMap(enduses,allenduses))
# filter down to conus
mappings.add_mapping(FilterToSubsetMap(states,conus_states))
mappings.add_mapping(FilterToSubsetMap(counties,conus_counties))
# then go back to vanilla enumerations
mappings.add_mapping(ExplicitAggregation.create_from_csv(conus_states,states,os.path.join(enumdata_folder,'conus_states_to_states.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(conus_counties,counties,os.path.join(enumdata_folder,'conus_counties_to_counties.csv')))
# explicit aggregations
mappings.add_mapping(ExplicitAggregation.create_from_csv(hourly2012,daily2012,os.path.join(enumdata_folder,'hourly2012_to_daily2012.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(hourly2012,weekly2012,os.path.join(enumdata_folder,'hourly2012_to_weekly2012.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(hourly2012,seasons,os.path.join(enumdata_folder,'hourly2012_to_seasons.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(daily2012,weekly2012,os.path.join(enumdata_folder,'daily2012_to_weekly2012.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(daily2012,seasons,os.path.join(enumdata_folder,'daily2012_to_seasons.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(enduses,fuel_types,os.path.join(enumdata_folder,'enduses_to_fuel_types.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(states,loss_state_groups,os.path.join(enumdata_folder,'states_to_loss_state_groups.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(states,census_divisions,os.path.join(enumdata_folder,'states_to_census_divisions.csv')))
mappings.add_mapping(ExplicitAggregation.create_from_csv(census_divisions,census_regions,os.path.join(enumdata_folder,'census_divisions_to_census_regions.csv')))
