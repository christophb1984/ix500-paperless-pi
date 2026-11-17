#!/usr/bin/env python3
"""Bounded subprocess: discover/apply SANE options only while worker owns USB."""
import json
import sys
from control import MANAGED, backend_source, validate_profile, validate_value


def describe_options(device):
    result=[]
    for index,name,title,description,kind,unit,size,cap,constraint in device.get_options():
        if not name or kind==5: continue
        item=dict(name=name,title=title,description=description,active=not bool(cap&32),
                  editable=bool(cap&1) and kind in (0,1,2,3) and name not in MANAGED,
                  kind={0:'boolean',1:'integer',2:'number',3:'text'}.get(kind,'action'),unit=unit)
        if isinstance(constraint,tuple): item['range']=list(constraint)
        elif isinstance(constraint,list): item['choices']=constraint
        if kind in (1,2) and size>4:
            item.update(kind='vector',count=size//4,scalar='integer' if kind==1 else 'number')
        # Read by native index: names like scan also exist as Python methods.
        try:
            value=device.dev.get_option(index) if item['active'] and kind!=4 else None
            item['value']=value.tolist() if hasattr(value,'tolist') else value
        except (AttributeError,RuntimeError): item['value']=None
        result.append(item)
    return result


def apply_profile(device,profile):
    validate_profile(profile)
    # Set source/mode first; these can reload dependent options and allowed ranges.
    core={'source':backend_source(profile),'mode':profile['mode'],'resolution':profile['dpi'],
          'page-width':profile['width_mm'],'page-height':profile['height_mm'],
          'tl-x':0,'tl-y':0,'br-x':profile['width_mm'],'br-y':profile['height_mm'],'swskip':0}
    for name,value in core.items():
        option=next((o for o in describe_options(device) if o['name']==name),None)
        if not option:
            if name in ('source','mode','resolution'): raise ValueError('Kernoption fehlt: '+name)
            continue
        if not option['active']: continue
        # effective-page-extent: use dimensions actually accepted by the backend.
        if name in ('br-x','br-y'):
            page_name = 'page_width' if name == 'br-x' else 'page_height'
            value = getattr(device, page_name, value)
        # Core geometry is managed, but still respects the backend constraints.
        # managed-mm-rounding: let SANE quantize fixed-point millimetres.
        if name in ('page-width','page-height','tl-x','tl-y','br-x','br-y') and option['kind']=='number' and option.get('range'):
            option = option | {'range': [*option['range'][:2], 0]}
        try:
            validate_value(value,option)
            setattr(device,name.replace('-','_'),value)
        except ValueError as error:
            raise ValueError(name+': '+str(error)) from None
        except Exception as error:
            raise ValueError(name+': Treiberfehler ('+type(error).__name__+').') from None
    extras=profile['sane_options']
    # Backend descriptor order preserves common dependencies such as custom-gamma → gamma-table.
    names=[o['name'] for o in describe_options(device)]
    if set(extras)-set(names): raise ValueError('Unbekannte Geräteoption.')
    for name in names:
        if name not in extras: continue
        catalog=describe_options(device)
        try:
            validate_profile(profile | {'sane_options':{name:extras[name]}},catalog)
            setattr(device,name.replace('-','_'),extras[name])
        except ValueError as error:
            raise ValueError(name+': '+str(error)) from None
        except Exception as error:
            raise ValueError(name+': Treiberfehler ('+type(error).__name__+').') from None
    return describe_options(device)


def main():
    import sane
    sane.init()
    try:
        request=json.load(sys.stdin)
        device=sane.open(request['device'])
        try: options=apply_profile(device,request['profile'])
        finally: device.close()
        json.dump(dict(options=options,profile=request['profile']),sys.stdout)
        return 0
    except ValueError as error:
        print('IX500_OPTION_ERROR '+json.dumps({'error':str(error)[:400]}),file=sys.stderr)
        return 1
    except Exception as error:
        # Only a type name crosses this boundary for unknown native exceptions.
        print('IX500_OPTION_ERROR '+json.dumps({'error':'SANE-Abfrage fehlgeschlagen ('+type(error).__name__+').'}),file=sys.stderr)
        return 1
    finally: sane.exit()

if __name__=='__main__': sys.exit(main())
