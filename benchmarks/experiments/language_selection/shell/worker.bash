#!/usr/bin/env bash
# Isolated Bash ASCII scanners. Core work uses only Bash builtins and loops.
# Integer code-point frames preserve NUL without storing NUL in Bash strings.
set -u
export LC_ALL=C
declare -a CH=() F=() OUT=()
declare -A STOP=()
digits=0123456789
letters=abcdefghijklmnopqrstuvwxyz
for ((i=0; i<10; i++)); do CH[48+i]=${digits:i:1}; done
for ((i=0; i<26; i++)); do CH[97+i]=${letters:i:1}; done
configured=0

load_stop() {
    local count=${F[0]} ptr=1 j k length cp token valid
    (( count <= 10000 )) || return 1
    STOP=()
    for ((j=0; j<count; j++)); do
        (( ptr < ${#F[@]} )) || return 1
        length=${F[ptr]}
        ((ptr+=1))
        (( length <= 4096 && ptr+length <= ${#F[@]} )) || return 1
        token=''
        valid=1
        for ((k=0; k<length; k++)); do
            cp=${F[ptr+k]}
            (( cp <= 127 )) || return 1
            if (( (cp >= 97 && cp <= 122) || (cp >= 48 && cp <= 57) )); then
                token+="${CH[cp]}"
            else
                # Such a stop string cannot equal an emitted [a-z0-9]+ token.
                valid=0
            fi
        done
        ((ptr+=length))
        if (( valid )) && [[ -n "$token" ]]; then STOP["$token"]=1; fi
    done
    (( ptr == ${#F[@]} ))
}

scan_tokens() {
    local original=$1 query=$2 offset=$3 length=$4
    local i cp previous=-1 word boundary token=''
    OUT=()
    for ((i=0; i<length; i++)); do
        cp=${F[offset+i]}
        (( word = (cp >= 97 && cp <= 122) || (cp >= 48 && cp <= 57) || (original && cp >= 65 && cp <= 90) ))
        (( boundary = original && previous >= 97 && previous <= 122 && cp >= 65 && cp <= 90 ))
        if (( !word || boundary )) && [[ -n "$token" ]]; then
            if (( !query )) || [[ ${STOP[$token]+present} != present ]]; then OUT+=("$token"); fi
            token=''
        fi
        if (( word )); then
            previous=$cp
            if (( original && cp >= 65 && cp <= 90 )); then ((cp+=32)); fi
            token+="${CH[cp]}"
        else
            previous=$cp
        fi
    done
    if [[ -n "$token" ]]; then
        if (( !query )) || [[ ${STOP[$token]+present} != present ]]; then OUT+=("$token"); fi
    fi
}

printf 'READY 1\n'
while IFS= read -r line; do
    if [[ "$line" == X ]]; then printf 'BYE\n'; break; fi
    kind=${line:0:1}
    if [[ ${line:1:1} != ' ' ]]; then printf 'ERR frame\n'; continue; fi
    payload=${line:2}
    # Canonical nonnegative decimals avoid arithmetic-expression evaluation and octal ambiguity.
    if [[ ! $payload =~ ^(0|[1-9][0-9]{0,8})([[:blank:]]+(0|[1-9][0-9]{0,8}))*$ ]]; then
        printf 'ERR numbers\n'
        continue
    fi
    read -r -a F <<< "$payload"
    if [[ "$kind" == S ]]; then
        if load_stop; then
            configured=1
            printf 'ACK STOP\n'
        else
            configured=0
            printf 'ERR stop\n'
        fi
        continue
    fi
    if (( !configured )); then printf 'ERR unconfigured\n'; continue; fi
    if [[ "$kind" == Q ]]; then
        (( ${#F[@]} >= 3 )) || { printf 'ERR shape\n'; continue; }
        repetitions=1
        original=${F[0]}
        query=${F[1]}
        length=${F[2]}
        offset=3
    elif [[ "$kind" == R ]]; then
        (( ${#F[@]} >= 4 )) || { printf 'ERR shape\n'; continue; }
        repetitions=${F[0]}
        original=${F[1]}
        query=${F[2]}
        length=${F[3]}
        offset=4
    else
        printf 'ERR command\n'
        continue
    fi
    if (( original > 1 || query > 1 || repetitions < 1 || repetitions > 100000 || length > 1000000 || ${#F[@]} != offset+length )); then
        printf 'ERR shape\n'
        continue
    fi
    valid=1
    for ((i=0; i<length; i++)); do
        if (( F[offset+i] > 127 )); then valid=0; break; fi
    done
    if (( !valid )); then printf 'ERR ascii\n'; continue; fi
    for ((run=0; run<repetitions; run++)); do
        scan_tokens "$original" "$query" "$offset" "$length"
    done
    printf 'OK %d' "${#OUT[@]}"
    if (( ${#OUT[@]} )); then printf ' %s' "${OUT[@]}"; fi
    printf '\n'
done
