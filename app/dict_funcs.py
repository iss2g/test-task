def path_analize(d: dict, path):
    for i, key in enumerate(path):
        if d.get(key):
            d = d[key]
        else:
            return {'ok': path[:i], 'miss': path[i:]}
    return {'ok': path[:i], 'miss': []}


def inite_path(d: dict, path, path_value=None):
    ok, miss = path_analize(d, path).values()
    d_temp = d
    for k in ok:
        d_temp = d_temp[k]
    for k in miss:
        d_temp[k] = {}
        d_temp = d_temp[k]
    replace_by_path(d, path, path_value)


def max_deep(d: dict):
    '''
    return max lenght of path in dict
    '''
    key_lenght = []
    for k in d:
        if isinstance(d[k], dict):
            lenght = 1 + max_deep(d[k])
            key_lenght.append(lenght)
        else:
            key_lenght.append(1)
    key_lenght.append(0)
    return max(key_lenght)


def get_by_path(d: dict, path):
    '''
    return value by path (a list with a sequence of dictionary keys)
    '''
    d_temp = d
    for k in path:
        d_temp = d_temp[k]
    return d_temp


def get_paths(d: dict, to_level=None):
    '''
    returns all dictionary paths (lists with a sequence of dictionary keys)

    '''
    paths = []

    if isinstance(to_level, int):
        if to_level:
            for k in d:
                if isinstance(d[k], dict):
                    local_paths = dict_get_paths(d[k], to_level - 1)
                    if local_paths:
                        for p in local_paths:
                            p.insert(0, k)
                            paths.append(p)
                    else:
                        paths.append([k])
                else:
                    paths.append([k])
            return paths
        else:
            return paths

    else:
        for k in d:
            if isinstance(d[k], dict):
                local_paths = dict_get_paths(d[k])
                if local_paths:
                    for p in local_paths:
                        p.insert(0, k)
                        paths.append(p)
                else:
                    paths.append(k)
            else:
                paths.append([k])
        return paths


def replace_by_path(d, inplace, path):
    d_temp = d
    for k in path[:-1]:
        d_temp = d_temp[k]
    d_temp[path[-1]] = inplace


def replace_not_dict_values(d: dict, inplace=None):
    for key, value in d.items():
        if not isinstance(value, dict):
            d[key] = inplace
    return d


def replace_not_dict_values_deep(d: dict, inplace=None):
    for key, value in d.items():
        if not isinstance(value, dict):
            d[key] = inplace
        else:
            replace_not_dict_values_deep(value, inplace)
    return d


def consists_of_keys(d: dict, *keys):
    keys = list(set(keys))
    if len(d) == len(keys):
        for k in keys:
            if d.get(k, '__NONE__') == '__NONE__':
                return False
        return True
    return False




